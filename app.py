import streamlit as st
import google.generativeai as genai
import random
import PyPDF2
import re
import json
import io
import time
import numpy as np
import pandas as pd
from datetime import datetime
from PIL import Image
from streamlit_drawable_canvas import st_canvas
from streamlit_local_storage import LocalStorage

# --- COSTANTI E CONFIGURAZIONI ---
LISTA_MODELLI = [
    'gemini-3.6-flash',
    'gemini-3.5-flash',
    'gemini-3.5-flash-lite',
    'gemini-2.5-flash'
]

st.set_page_config(page_title="Nexus Study App", page_icon="🧬", layout="wide")

# --- TEMA PERSONALIZZATO (font + card riutilizzabili in tutta l'app) ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Sora:wght@400;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Sora', sans-serif;
}

h1, h2, h3 {
    font-weight: 700 !important;
    letter-spacing: -0.02em;
}

.stButton > button {
    border-radius: 10px;
    font-weight: 600;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.stButton > button:hover {
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(34, 211, 166, 0.25);
}

.nexus-card {
    background: linear-gradient(135deg, rgba(34,211,166,0.08), rgba(27,34,48,0.6));
    border: 1px solid rgba(34,211,166,0.25);
    border-radius: 16px;
    padding: 1.1rem 1.4rem;
    margin-bottom: 1rem;
}
.nexus-card h3 {
    margin: 0 0 0.3rem 0;
}
.nexus-card .nexus-sub {
    opacity: 0.75;
    font-size: 0.88rem;
    margin-bottom: 0.6rem;
}
.nexus-badge {
    display: inline-block;
    padding: 0.2rem 0.7rem;
    border-radius: 999px;
    font-size: 0.82rem;
    font-weight: 600;
}
.nexus-badge-green  { background: rgba(34,211,166,0.18); color: #22D3A6; }
.nexus-badge-orange { background: rgba(245,158,11,0.18); color: #F59E0B; }
.nexus-badge-red    { background: rgba(239,68,68,0.18);  color: #EF4444; }
</style>
""", unsafe_allow_html=True)


def badge_padronanza(media_voto):
    """Restituisce l'HTML di un badge colorato in base alla media dei voti."""
    if media_voto >= 80:
        classe, etichetta = "nexus-badge-green", "Padronanza alta"
    elif media_voto >= 50:
        classe, etichetta = "nexus-badge-orange", "Da consolidare"
    else:
        classe, etichetta = "nexus-badge-red", "Da ripassare"
    return f'<span class="nexus-badge {classe}">{etichetta} · {media_voto:.0f}%</span>'

# --- LOCAL STORAGE DEL BROWSER (isolato per ogni visitatore del link) ---
localS = LocalStorage()
CHIAVE_PROFILO_LOCALE = "nexus_profilo_v1"
CHIAVE_API_KEY_LOCALE = "nexus_api_key_v1"


def salva_profilo_locale(contesto="generico"):
    """Salva silenziosamente il profilo corrente nel local storage di QUESTO browser.
    Non blocca mai l'app: se il salvataggio fallisce per qualche motivo, l'utente
    ha comunque i pulsanti di Scarica/Carica manuale come rete di sicurezza."""
    try:
        localS.setItem(
            CHIAVE_PROFILO_LOCALE,
            json.dumps(st.session_state.database_domande)
        )
        time.sleep(0.3)  # dà tempo al browser di completare la scrittura
    except Exception:
        pass


if 'database_domande' not in st.session_state:
    st.session_state.database_domande = {}

if 'conferma_elimina' not in st.session_state:
    st.session_state.conferma_elimina = None

# Al primo caricamento della sessione, prova a ripristinare automaticamente
# il profilo salvato in precedenza in QUESTO browser.
if 'profilo_locale_caricato' not in st.session_state:
    st.session_state.profilo_locale_caricato = True
    profilo_salvato = localS.getItem(CHIAVE_PROFILO_LOCALE)
    if profilo_salvato:
        try:
            st.session_state.database_domande = json.loads(profilo_salvato)
        except (json.JSONDecodeError, TypeError):
            pass

# Stessa logica per l'API key, ma solo se l'utente ha esplicitamente
# scelto di farla ricordare (vedi checkbox in sidebar più sotto).
if 'api_key_locale_precaricata' not in st.session_state:
    valore_salvato = localS.getItem(CHIAVE_API_KEY_LOCALE)
    st.session_state.api_key_locale_precaricata = valore_salvato if valore_salvato else ""

# --- FUNZIONE MOTORE IA (MULTIMODALE CON FALLBACK) ---
def interroga_ai_con_fallback(prompt_testo, immagine_pill=None):
    """Prova i modelli in sequenza. Se c'è un'immagine, la invia insieme al testo."""
    for nome_modello in LISTA_MODELLI:
        try:
            modello = genai.GenerativeModel(nome_modello)
            if immagine_pill is not None:
                risposta = modello.generate_content([prompt_testo, immagine_pill])
            else:
                risposta = modello.generate_content(prompt_testo)
            return risposta.text
        except Exception as e:
            st.toast(f"⚠️ {nome_modello} occupato. Provo via secondaria...", icon="🔄")
            continue
    raise Exception("Tutti i modelli AI sono momentaneamente bloccati. Riprova tra poco.")


# --- FUNZIONE CORRETTA: composita il disegno (RGBA trasparente) su sfondo bianco ---
def prepara_immagine_lavagna(canvas_result):
    """
    st_canvas restituisce in image_data SOLO il livello disegnato, con alpha=0
    ovunque non si sia scritto nulla. Se si scarta l'alpha con .convert('RGB')
    senza comporre prima su uno sfondo bianco, tutta l'area non disegnata
    diventa NERA (0,0,0) e il tratto nero della penna sparisce dentro di essa:
    il risultato è un'immagine praticamente illeggibile per l'AI.
    Questa funzione compone correttamente il disegno su uno sfondo bianco reale.

    Prova prima `image_bytes` (PNG grezzo, introdotto nelle versioni più
    recenti della libreria) e solo se non disponibile ripiega su `image_data`
    (array numpy RGBA). Restituisce None se il canvas è vuoto o i dati non
    sono ancora arrivati dal frontend.
    """
    if canvas_result is None:
        return None

    # --- Tentativo 1: image_bytes (PNG grezzo) ---
    try:
        png_bytes = canvas_result.image_bytes
    except (RuntimeError, AttributeError):
        png_bytes = None

    if png_bytes:
        try:
            disegno_png = Image.open(io.BytesIO(png_bytes)).convert('RGBA')
            sfondo_bianco_png = Image.new('RGBA', disegno_png.size, (255, 255, 255, 255))
            return Image.alpha_composite(sfondo_bianco_png, disegno_png).convert('RGB')
        except Exception:
            pass  # se la decodifica fallisce, proviamo comunque la via classica

    # --- Tentativo 2: image_data (array numpy RGBA) ---
    try:
        dati_immagine = canvas_result.image_data
    except RuntimeError:
        # Capita se return_image_data=True non è stato passato a st_canvas,
        # oppure se il componente non ha ancora inviato dati (canvas appena montato).
        return None

    if dati_immagine is None:
        return None

    img_array = dati_immagine.astype('uint8')

    # Canale alpha tutto a zero = non è stato disegnato nulla
    if img_array.shape[-1] == 4 and img_array[:, :, 3].max() == 0:
        return None

    disegno_rgba = Image.fromarray(img_array, 'RGBA')
    sfondo_bianco = Image.new('RGBA', disegno_rgba.size, (255, 255, 255, 255))
    immagine_finale = Image.alpha_composite(sfondo_bianco, disegno_rgba)
    return immagine_finale.convert('RGB')


# --- FUNZIONE PER IL RIPASSO INTELLIGENTE (SPACED REPETITION SEMPLIFICATA) ---
def calcola_priorita_domanda(domanda):
    """
    Assegna un peso più alto alle domande che meritano più attenzione:
    - mai risposte -> priorità massima
    - voto basso -> priorità alta
    - non ripassate da molto tempo -> priorità che cresce nel tempo
    Restituisce (peso, motivo_leggibile) da mostrare all'utente per trasparenza.
    """
    storico = domanda.get("storico", [])

    if not storico:
        return 100.0, "non hai mai risposto a questa domanda"

    ultimo = storico[-1]
    ultimo_voto = ultimo.get("voto", 0)

    try:
        data_ultimo = datetime.strptime(ultimo["data"], "%Y-%m-%d %H:%M")
        giorni_trascorsi = (datetime.now() - data_ultimo).days
    except (ValueError, KeyError):
        giorni_trascorsi = 0

    priorita_da_voto = max(5, 100 - ultimo_voto)  # voto basso -> priorità alta
    fattore_tempo = 1 + min(giorni_trascorsi, 30) / 10.0  # cresce nel tempo, con un tetto a 30 giorni
    peso = priorita_da_voto * fattore_tempo

    quando = "oggi" if giorni_trascorsi <= 0 else (
        "ieri" if giorni_trascorsi == 1 else f"{giorni_trascorsi} giorni fa"
    )
    motivo = f"ultimo voto {ultimo_voto}%, risposto {quando}"
    return peso, motivo


# --- BARRA LATERALE E GESTIONE PROFILO ---
st.sidebar.title("🧬 Nexus Ecosistema")
api_key = st.sidebar.text_input(
    "Inserisci la tua API Key:",
    type="password",
    value=st.session_state.api_key_locale_precaricata
)

ricorda_api_key = st.sidebar.checkbox(
    "🔒 Ricorda la mia API Key su questo browser",
    value=bool(st.session_state.api_key_locale_precaricata),
    help="Salvata solo nel local storage di QUESTO browser, mai su un server. "
         "Non abilitarla su dispositivi condivisi o pubblici."
)

if ricorda_api_key and api_key and api_key != st.session_state.api_key_locale_precaricata:
    localS.setItem(CHIAVE_API_KEY_LOCALE, api_key)
    st.session_state.api_key_locale_precaricata = api_key
elif not ricorda_api_key and st.session_state.api_key_locale_precaricata:
    localS.setItem(CHIAVE_API_KEY_LOCALE, "")
    st.session_state.api_key_locale_precaricata = ""

if api_key:
    genai.configure(api_key=api_key)
else:
    st.sidebar.warning("Inserisci la chiave per attivare l'AI.")

st.sidebar.markdown("---")
st.sidebar.subheader("💾 Il tuo Profilo di Studio")
st.sidebar.caption(
    "✅ Salvataggio automatico attivo in questo browser. "
    "Scarica comunque un backup se vuoi portare i progressi su un altro dispositivo."
)

if st.sidebar.button("🔄 Forza sincronizzazione ora"):
    salva_profilo_locale("manuale")
    st.sidebar.success("Profilo sincronizzato con il local storage!")

dati_json = json.dumps(st.session_state.database_domande, indent=4)
st.sidebar.download_button(
    label="⬇️ Scarica il mio Profilo (backup)",
    data=dati_json,
    file_name="Mio_Profilo_Nexus.json",
    mime="application/json"
)

file_profilo = st.sidebar.file_uploader("⬆️ Carica il tuo Profilo", type="json")
if file_profilo is not None:
    if 'profilo_caricato' not in st.session_state:
        st.session_state.database_domande = json.load(file_profilo)
        st.session_state.profilo_caricato = True
        salva_profilo_locale("upload")
        st.sidebar.success("Profilo ripristinato con successo!")
        st.rerun()

st.sidebar.markdown("---")
modalita = st.sidebar.radio("Navigazione:", ["🏠 Home & Istruzioni", "⚙️ Aggiungi PDF", "🎙️ Simulazione Esame", "📈 Dashboard Mastery"])

# ==========================================
# MODULO 1: HOME & ISTRUZIONI (Versione Integrale)
# ==========================================
if modalita == "🏠 Home & Istruzioni":
    if not st.session_state.database_domande:
        st.title("Benvenuto in Nexus Study 🧬")
        st.write("La piattaforma dinamica per preparare i tuoi esami universitari tramite *Active Recall* e Intelligenza Artificiale.")

        st.markdown("---")
        st.subheader("🚀 Guida Rapida in 3 Step")

        col1, col2, col3 = st.columns(3)
        with col1:
            st.info("**1. Accendi il Motore**\n\nOttieni una API Key da [Google AI Studio](https://aistudio.google.com/app/apikey) e incollala qui a sinistra.")
        with col2:
            st.info("**2. Fornisci il Materiale**\n\nVai su **⚙️ Aggiungi PDF**, crea una materia e carica le dispense. L'AI genererà domande specifiche.")
        with col3:
            st.error("**3. SALVA IL TUO PROFILO!**\n\nNessun dato viene salvato sul server. Scarica il Profilo a sinistra a fine sessione per non perdere i voti.")

        st.markdown("---")
        st.subheader("💡 Consigli per l'Esame")
        st.markdown("""
        * **Nuova Modalità Multimodale:** Nella sezione Simulazione, ora puoi scegliere di scrivere a tastiera o usare la **Lavagna Interattiva** per disegnare strutture e grafici.
        * **Carica a blocchi:** Inserisci PDF divisi per capitoli per avere domande più precise.
        * **Resistenza ai Crash:** Il sistema ha un fallback automatico. Se un modello esaurisce i tentativi, passerà a uno di riserva silenziosamente.
        """)
    else:
        st.title("🏠 Il tuo Ecosistema di Studio")

        tot_materie = len(st.session_state.database_domande)
        tot_argomenti = sum(len(argomenti) for argomenti in st.session_state.database_domande.values())
        tot_domande = sum(len(domande) for argomenti in st.session_state.database_domande.values() for domande in argomenti.values())

        col1, col2, col3 = st.columns(3)
        col1.metric("📚 Materie Inserite", tot_materie)
        col2.metric("📁 Argomenti Estrapolati", tot_argomenti)
        col3.metric("❓ Domande Generate", tot_domande)

        st.markdown("---")
        for materia, argomenti in st.session_state.database_domande.items():
            domande_materia = [d for lista in argomenti.values() for d in lista]
            n_domande = len(domande_materia)
            voti = [d['punteggio'] for d in domande_materia if d.get('storico')]
            media_voto = sum(voti) / len(voti) if voti else 0.0
            badge = badge_padronanza(media_voto) if voti else '<span class="nexus-badge nexus-badge-orange">Ancora da iniziare</span>'
            tags = " &nbsp;·&nbsp; ".join([f"<i>{arg}</i>" for arg in argomenti.keys()])

            st.markdown(f"""
            <div class="nexus-card">
                <h3>🧬 {materia}</h3>
                <div class="nexus-sub">{len(argomenti)} argomenti &nbsp;|&nbsp; {n_domande} domande totali</div>
                {badge}
                <div style="margin-top:0.6rem; opacity:0.85; font-size:0.9rem;">{tags}</div>
            </div>
            """, unsafe_allow_html=True)

        with st.expander("📖 Rileggi la Guida all'Uso e i Consigli"):
            st.write("1. **API Key:** Ottienila gratis da Google AI Studio e incollala a sinistra.")
            st.write("2. **Privacy:** Ricordati sempre di scaricare il tuo profilo (file JSON) a fine sessione!")
            st.write("3. **Simulazione:** Puoi usare la tastiera o la lavagna interattiva per disegnare e rispondere.")

# ==========================================
# MODULO 2: LETTURA PDF
# ==========================================
elif modalita == "⚙️ Aggiungi PDF":
    st.title("⚙️ Estrazione Massiva per Argomenti")

    col1, col2 = st.columns(2)
    with col1:
        materie_esistenti = list(st.session_state.database_domande.keys())
        scelta_materia = st.selectbox("Materia:", ["-- Nuova Materia --"] + materie_esistenti)
    with col2:
        nuova_materia = st.text_input("Oppure crea Nuova Materia:")

    materia_target = nuova_materia if nuova_materia else (scelta_materia if scelta_materia != "-- Nuova Materia --" else None)
    tipo_esame = st.radio("Tipo di esame:", ["Orale (Discorsive)", "Scritto (Specifiche)"])
    file_pdf = st.file_uploader("Carica dispense PDF", type="pdf")

    if st.button("Genera Domande da tutto il PDF"):
        if not api_key or not materia_target or not file_pdf:
            st.error("Assicurati di aver inserito chiave, materia e file.")
        else:
            with st.spinner("Estrazione argomenti e generazione domande... ⏳"):
                try:
                    lettore = PyPDF2.PdfReader(file_pdf)
                    testo_estratto = "".join([pagina.extract_text() for pagina in lettore.pages])

                    prompt = f"""
                    Agisci come professore di {materia_target}. Leggi: "{testo_estratto}"
                    Identifica i macro-argomenti e genera 3-5 domande per un esame {tipo_esame}.
                    FORMATO ESATTO RICHIESTO:
                    ### ARGOMENTO: [Nome]
                    - [Domanda 1]
                    - [Domanda 2]
                    """
                    testo_risposta_ai = interroga_ai_con_fallback(prompt)

                    if materia_target not in st.session_state.database_domande:
                        st.session_state.database_domande[materia_target] = {}

                    righe = testo_risposta_ai.strip().split('\n')
                    argomento_corrente = "Varie"
                    totale_domande = 0

                    for riga in righe:
                        riga = riga.strip()
                        if riga.startswith("### ARGOMENTO:"):
                            argomento_corrente = riga.replace("### ARGOMENTO:", "").strip()
                            if argomento_corrente not in st.session_state.database_domande[materia_target]:
                                st.session_state.database_domande[materia_target][argomento_corrente] = []
                        elif riga.startswith("- "):
                            domanda_testo = riga.replace("- ", "").strip()
                            st.session_state.database_domande[materia_target][argomento_corrente].append({"testo": domanda_testo, "punteggio": 0, "storico": []})
                            totale_domande += 1

                    salva_profilo_locale("pdf")
                    st.success(f"✅ Generate {totale_domande} domande. Salvate automaticamente in questo browser!")
                except Exception as e:
                    st.error(f"Errore critico: {e}")

# ==========================================
# MODULO 3: SIMULAZIONE (MOTORE MULTIMODALE - CORRETTO)
# ==========================================
elif modalita == "🎙️ Simulazione Esame":
    st.title("🎙️ Simulazione Interattiva")

    materia_quiz = st.selectbox("Scegli la materia:", list(st.session_state.database_domande.keys()) if st.session_state.database_domande else [])

    if not materia_quiz:
        st.warning("Aggiungi prima una materia o carica il tuo profilo.")
    else:
        argomenti_disponibili = list(st.session_state.database_domande[materia_quiz].keys())
        argomento_scelto = st.selectbox("Focus sull'argomento:", ["Mix Casuale (Tutto)"] + argomenti_disponibili)

        modalita_scelta_domanda = st.radio(
            "Come scegliere la prossima domanda:",
            ["🧠 Ripasso Intelligente (consigliata)", "🎲 Casuale pura"],
            horizontal=True,
            help="Il Ripasso Intelligente dà priorità alle domande mai fatte, con voto basso, o non ripassate da tempo."
        )

        if 'domanda_ai' not in st.session_state or st.button("🔄 Prossima Domanda"):
            # Costruisce il pool di domande su cui pescare, in base al filtro argomento
            if argomento_scelto == "Mix Casuale (Tutto)":
                pool_domande = [d for arg in argomenti_disponibili for d in st.session_state.database_domande[materia_quiz][arg]]
            else:
                pool_domande = st.session_state.database_domande[materia_quiz][argomento_scelto]

            if modalita_scelta_domanda.startswith("🧠"):
                pesi_e_motivi = [calcola_priorita_domanda(d) for d in pool_domande]
                pesi = [p for p, _ in pesi_e_motivi]
                indice_scelto = random.choices(range(len(pool_domande)), weights=pesi, k=1)[0]
                st.session_state.domanda_ai = pool_domande[indice_scelto]
                st.session_state.motivo_scelta_domanda = pesi_e_motivi[indice_scelto][1]
            else:
                st.session_state.domanda_ai = random.choice(pool_domande)
                st.session_state.motivo_scelta_domanda = "selezione casuale"

        st.info(f"**Domanda:** {st.session_state.domanda_ai['testo']}")
        st.caption(
            f"Ultimo punteggio: {st.session_state.domanda_ai['punteggio']}%  ·  "
            f"🧠 Scelta perché: {st.session_state.get('motivo_scelta_domanda', 'prima domanda della sessione')}"
        )

        # --- SCELTA DELLA MODALITA' DI RISPOSTA ---
        tipo_risposta = st.radio("Scegli come rispondere:", ["⌨️ Testo Classico", "🖍️ Lavagna Interattiva (Disegno/Formule)"])

        risposta_testuale = ""
        nota_aggiuntiva = ""
        canvas_result = None

        if tipo_risposta == "⌨️ Testo Classico":
            risposta_testuale = st.text_area("Scrivi qui la tua risposta:", height=150)

        elif tipo_risposta == "🖍️ Lavagna Interattiva (Disegno/Formule)":
            st.write("Usa il mouse o il pennino per disegnare le tue formule o grafici.")

            col_tool, col_size = st.columns([2, 1])
            with col_tool:
                tipo_strumento = st.radio(
                    "Strumento:",
                    ["✏️ Penna", "🧼 Gomma", "📏 Linea", "⭕ Cerchio", "🟩 Rettangolo"],
                    horizontal=True
                )
            with col_size:
                stroke_width = st.slider("Spessore tratto:", 1, 15, 3)

            drawing_mode = "freedraw"
            stroke_color = "#000000"

            if tipo_strumento == "✏️ Penna": drawing_mode = "freedraw"
            elif tipo_strumento == "🧼 Gomma":
                drawing_mode = "freedraw"
                stroke_color = "#FFFFFF"
                stroke_width = stroke_width + 5
            elif tipo_strumento == "📏 Linea": drawing_mode = "line"
            elif tipo_strumento == "⭕ Cerchio": drawing_mode = "circle"
            elif tipo_strumento == "🟩 Rettangolo": drawing_mode = "rect"

            foglio_di_carta = Image.new("RGB", (700, 350), (255, 255, 255))

            canvas_result = st_canvas(
                fill_color="rgba(0, 0, 0, 0)",
                stroke_width=stroke_width,
                stroke_color=stroke_color,
                background_image=foglio_di_carta,
                width=700,
                height=350,
                drawing_mode=drawing_mode,
                return_image_data=True,  # OBBLIGATORIO da streamlit-drawable-canvas 0.10.0: senza questo, .image_data solleva RuntimeError
                key="canvas_principale_univoco",
            )

            st.caption("Nota: Puoi lasciare vuoto il campo di testo se hai risposto interamente con il disegno.")
            nota_aggiuntiva = st.text_input(
                "Aggiungi una nota testuale opzionale al tuo disegno:",
                key="testo_lavagna_univoco"
            )

        # --- INVIO AL PROFESSORE ---
        if st.button("Invia per la correzione"):
            # Ricalcoliamo l'immagine QUI, nello stesso run del click, usando
            # direttamente canvas_result (niente più dipendenza da session_state
            # scritta in un try/except silenzioso).
            immagine_da_inviare = None
            testo_per_ai = risposta_testuale

            if tipo_risposta == "🖍️ Lavagna Interattiva (Disegno/Formule)":
                immagine_da_inviare = prepara_immagine_lavagna(canvas_result)
                testo_per_ai = nota_aggiuntiva

            if testo_per_ai.strip() == "" and immagine_da_inviare is None:
                st.warning("Inserisci una risposta testuale o fai un disegno sulla lavagna!")
            elif api_key:
                with st.spinner("Il professore sta analizzando il tuo elaborato... ⏳"):
                    try:
                        prompt_prof = f"""Sei un professore universitario di {materia_quiz}, rigoroso ma costruttivo nel tono.

DOMANDA D'ESAME:
"{st.session_state.domanda_ai['testo']}"

RISPOSTA DELLO STUDENTE (testo e/o immagine allegata):
Testo: "{testo_per_ai if testo_per_ai.strip() else '(nessuna nota testuale, vedi solo immagine)'}"

ISTRUZIONI - segui questi passaggi ESATTAMENTE in ordine:

1. TRASCRIZIONE FEDELE: prima di tutto, descrivi SOLO ciò che è effettivamente visibile o scritto nella risposta (formule, testo, disegni). Non aggiungere, completare o correggere mentalmente nulla che lo studente non abbia realmente scritto, anche se ti aspetteresti di vederlo per rispondere pienamente alla domanda. Se la scrittura è poco leggibile o ambigua, dillo esplicitamente invece di indovinare.

2. CONFRONTO CON LA DOMANDA: elenca esplicitamente quali punti richiesti dalla domanda sono stati affrontati nella trascrizione del punto 1, e quali invece MANCANO o sono incompleti. Sii specifico.

3. VOTO ONESTO: un voto alto (90-100%) richiede che OGNI parte della domanda sia stata trattata correttamente in ciò che lo studente ha realmente scritto. Se lo studente ha svolto solo una parte della domanda (anche se quella parte è perfetta), il voto deve riflettere la percentuale di domanda effettivamente coperta, non la qualità della sola parte svolta. Non essere generoso per incoraggiamento: sii onesto, il tono incoraggiante va nel testo dell'analisi, non nel voto.

FORMATO DI OUTPUT RICHIESTO (rispetta esattamente questa struttura):
Riga 1: SOLO il voto da 0 a 100 seguito da % (Es: 65%)
Poi:
**Cosa hai scritto:** [la trascrizione fedele del punto 1]
**Cosa manca rispetto alla domanda:** [punto 2, oppure "Nulla, hai coperto tutta la domanda" se è davvero così]
**Analisi:** [valutazione di ciò che hai scritto]
**Trucco Mnemonico:** [...]"""

                        risposta_finale = interroga_ai_con_fallback(prompt_prof, immagine_pill=immagine_da_inviare)

                        match = re.search(r'(\d{1,3})%', risposta_finale)
                        if match:
                            voto = int(match.group(1))
                            st.session_state.domanda_ai['punteggio'] = voto

                            # Compatibilità con profili salvati prima dell'introduzione dello storico
                            if 'storico' not in st.session_state.domanda_ai:
                                st.session_state.domanda_ai['storico'] = []
                            st.session_state.domanda_ai['storico'].append({
                                "data": datetime.now().strftime("%Y-%m-%d %H:%M"),
                                "voto": voto
                            })

                            salva_profilo_locale("voto")
                            if voto >= 90: st.balloons()

                        st.write(risposta_finale)

                        # Utile per verificare visivamente cosa è stato davvero inviato all'AI
                        if immagine_da_inviare is not None:
                            with st.expander("🔍 Immagine effettivamente inviata all'AI"):
                                st.image(immagine_da_inviare)
                    except Exception as e:
                        st.error(f"Errore critico AI: {e}")
            else:
                st.error("Inserisci l'API Key nella barra laterale per usare questa funzione.")

# ==========================================
# MODULO 4: DASHBOARD MASTERY (Versione Integrale)
# ==========================================
elif modalita == "📈 Dashboard Mastery":
    st.title("📈 Dashboard a Espansione")
    st.write("Apri gli argomenti per visualizzare le domande. Clicca sui pulsanti per generare nuove domande al volo.")

    materia_dash = st.selectbox("Analizza la materia:", list(st.session_state.database_domande.keys()) if st.session_state.database_domande else [])

    if materia_dash:
        argomenti = st.session_state.database_domande[materia_dash]

        # --- ARGOMENTO CONSIGLIATO PER IL RIPASSO (stessa logica del Ripasso Intelligente) ---
        priorita_per_argomento = {}
        for nome_arg, lista_d in argomenti.items():
            if lista_d:
                pesi = [calcola_priorita_domanda(d)[0] for d in lista_d]
                priorita_per_argomento[nome_arg] = sum(pesi) / len(pesi)

        if priorita_per_argomento:
            argomento_consigliato = max(priorita_per_argomento, key=priorita_per_argomento.get)
            st.info(f"🎯 **Argomento consigliato per il prossimo ripasso:** {argomento_consigliato}")

        # --- RACCOLTA DI TUTTO LO STORICO DELLA MATERIA (per i grafici) ---
        storico_completo = []
        for nome_arg, lista_d in argomenti.items():
            for d in lista_d:
                for voce in d.get("storico", []):  # .get() per compatibilità con profili vecchi
                    storico_completo.append({
                        "data": voce["data"],
                        "voto": voce["voto"],
                        "argomento": nome_arg
                    })

        st.subheader("📈 Andamento nel tempo")
        if storico_completo:
            df_storico = pd.DataFrame(storico_completo)
            df_storico["data"] = pd.to_datetime(df_storico["data"])
            df_storico["giorno"] = df_storico["data"].dt.date
            andamento_giornaliero = df_storico.groupby("giorno")["voto"].mean()
            st.line_chart(andamento_giornaliero)
            st.caption("Media dei voti ottenuti per giorno, su tutta la materia.")
        else:
            st.info("Non hai ancora correzioni registrate con data. Rispondi ad alcune domande in 🎙️ Simulazione Esame per iniziare a popolare questo grafico.")

        st.markdown("---")

        for nome_argomento, lista_domande in list(argomenti.items()):
            voti_argomento = [d['punteggio'] for d in lista_domande if d.get('storico')]
            media_argomento = sum(voti_argomento) / len(voti_argomento) if voti_argomento else None

            with st.expander(f"📁 {nome_argomento} ({len(lista_domande)} domande)"):

                if media_argomento is not None:
                    st.markdown(badge_padronanza(media_argomento), unsafe_allow_html=True)
                else:
                    st.markdown('<span class="nexus-badge nexus-badge-orange">Ancora da iniziare</span>', unsafe_allow_html=True)

                chiave_arg = f"argomento::{materia_dash}::{nome_argomento}"

                col_genera, col_elimina_arg = st.columns([3, 1])
                with col_genera:
                    # --- PULSANTE MAGICO PER GENERARE ALTRE DOMANDE ---
                    if st.button(f"➕ Genera 1 nuova domanda su '{nome_argomento}'", key=f"btn_{nome_argomento}"):
                        if api_key:
                            with st.spinner("Creazione in corso... ⏳"):
                                prompt_nuova = f"Sei un professore universitario. Genera UNA singola domanda d'esame complessa sulla materia '{materia_dash}', focalizzata in particolare sull'argomento '{nome_argomento}'. Restituisci SOLO il testo della domanda, senza numerazione o altro."
                                try:
                                    nuova_domanda = interroga_ai_con_fallback(prompt_nuova).strip()

                                    if nuova_domanda:
                                        st.session_state.database_domande[materia_dash][nome_argomento].append({"testo": nuova_domanda, "punteggio": 0, "storico": []})
                                        salva_profilo_locale("dashboard")
                                        st.success("Domanda aggiunta con successo!")
                                        st.rerun()
                                except Exception as e:
                                    st.error(f"Errore durante la generazione: {e}")
                        else:
                            st.error("Inserisci l'API Key nella barra laterale per usare questa funzione.")
                with col_elimina_arg:
                    if st.button("🗑️ Elimina argomento", key=f"del_arg_{nome_argomento}"):
                        st.session_state.conferma_elimina = chiave_arg
                        st.rerun()

                if st.session_state.conferma_elimina == chiave_arg:
                    st.warning(f"⚠️ Eliminare tutto l'argomento **'{nome_argomento}'** e le sue {len(lista_domande)} domande? Non è reversibile (a meno di ricaricare un backup precedente).")
                    col_si, col_no = st.columns(2)
                    with col_si:
                        if st.button("✅ Sì, elimina definitivamente", key=f"conferma_del_arg_{nome_argomento}"):
                            del st.session_state.database_domande[materia_dash][nome_argomento]
                            st.session_state.conferma_elimina = None
                            salva_profilo_locale("elimina_argomento")
                            st.success(f"Argomento '{nome_argomento}' eliminato.")
                            st.rerun()
                    with col_no:
                        if st.button("❌ Annulla", key=f"annulla_del_arg_{nome_argomento}"):
                            st.session_state.conferma_elimina = None
                            st.rerun()

                # --- GRAFICO DI ANDAMENTO SPECIFICO PER QUESTO ARGOMENTO ---
                storico_argomento = [v for v in storico_completo if v["argomento"] == nome_argomento]
                if storico_argomento:
                    df_arg = pd.DataFrame(storico_argomento).sort_values("data")
                    df_arg["data"] = pd.to_datetime(df_arg["data"])
                    st.line_chart(df_arg.set_index("data")["voto"])

                st.markdown("---")

                # Lista delle domande con le barre di progresso e l'eliminazione singola
                for idx, d in enumerate(lista_domande):
                    chiave_dom = f"domanda::{materia_dash}::{nome_argomento}::{idx}"
                    col_testo, col_barra, col_elimina_d = st.columns([3, 1, 1])
                    with col_testo:
                        st.write(f"**{idx + 1}.** {d['testo']}")
                    with col_barra:
                        st.progress(d['punteggio'] / 100)
                        if d['punteggio'] == 100:
                            st.success("100%")
                        elif d['punteggio'] >= 60:
                            st.warning(f"{d['punteggio']}%")
                        else:
                            st.error(f"{d['punteggio']}%")
                    with col_elimina_d:
                        if st.button("🗑️", key=f"del_dom_{nome_argomento}_{idx}", help="Elimina questa domanda"):
                            st.session_state.conferma_elimina = chiave_dom
                            st.rerun()

                    if st.session_state.conferma_elimina == chiave_dom:
                        st.warning("Eliminare questa domanda?")
                        col_si_d, col_no_d = st.columns(2)
                        with col_si_d:
                            if st.button("✅ Conferma", key=f"conferma_del_dom_{nome_argomento}_{idx}"):
                                del st.session_state.database_domande[materia_dash][nome_argomento][idx]
                                st.session_state.conferma_elimina = None
                                salva_profilo_locale("elimina_domanda")
                                st.rerun()
                        with col_no_d:
                            if st.button("❌ Annulla", key=f"annulla_del_dom_{nome_argomento}_{idx}"):
                                st.session_state.conferma_elimina = None
                                st.rerun()
