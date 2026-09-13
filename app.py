import streamlit as st
import google.generativeai as genai
import random
import PyPDF2
import re
import json
import numpy as np
from PIL import Image
from streamlit_drawable_canvas import st_canvas

# --- COSTANTI E CONFIGURAZIONI ---
LISTA_MODELLI = [
    'gemini-3.6-flash',
    'gemini-3.5-flash',
    'gemini-3.5-flash-lite',
    'gemini-2.5-flash'
]

st.set_page_config(page_title="Nexus Study App", page_icon="🧬", layout="wide")

if 'database_domande' not in st.session_state:
    st.session_state.database_domande = {}

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

# --- BARRA LATERALE E GESTIONE PROFILO ---
st.sidebar.title("🧬 Nexus Ecosistema")
api_key = st.sidebar.text_input("Inserisci la tua API Key:", type="password")

if api_key:
    genai.configure(api_key=api_key)
else:
    st.sidebar.warning("Inserisci la chiave per attivare l'AI.")

st.sidebar.markdown("---")
st.sidebar.subheader("💾 Il tuo Profilo di Studio")
st.sidebar.caption("L'app non salva dati sul server. Scarica i tuoi progressi a fine sessione!")

dati_json = json.dumps(st.session_state.database_domande, indent=4)
st.sidebar.download_button(
    label="⬇️ Scarica il mio Profilo",
    data=dati_json,
    file_name="Mio_Profilo_Nexus.json",
    mime="application/json"
)

file_profilo = st.sidebar.file_uploader("⬆️ Carica il tuo Profilo", type="json")
if file_profilo is not None:
    if 'profilo_caricato' not in st.session_state:
        st.session_state.database_domande = json.load(file_profilo)
        st.session_state.profilo_caricato = True
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
            with st.container():
                st.markdown(f"### 🧬 {materia}")
                domande_materia = sum(len(d) for d in argomenti.values())
                st.caption(f"{len(argomenti)} Argomenti | {domande_materia} Domande totali")
                tags = " | ".join([f"*{arg}*" for arg in argomenti.keys()])
                st.write(tags)
                st.markdown("---")
        
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
                            st.session_state.database_domande[materia_target][argomento_corrente].append({"testo": domanda_testo, "punteggio": 0})
                            totale_domande += 1
                    
                    st.success(f"✅ Generate {totale_domande} domande. Ricordati di SCARICARE IL PROFILO prima di uscire!")
                except Exception as e:
                    st.error(f"Errore critico: {e}")
# ==========================================
# MODULO 3: SIMULAZIONE (IL NUOVO MOTORE MULTIMODALE)
# ==========================================
elif modalita == "🎙️ Simulazione Esame":
    st.title("🎙️ Simulazione Interattiva")
    
    materia_quiz = st.selectbox("Scegli la materia:", list(st.session_state.database_domande.keys()) if st.session_state.database_domande else [])
    
    if not materia_quiz:
        st.warning("Aggiungi prima una materia o carica il tuo profilo.")
    else:
        argomenti_disponibili = list(st.session_state.database_domande[materia_quiz].keys())
        argomento_scelto = st.selectbox("Focus sull'argomento:", ["Mix Casuale (Tutto)"] + argomenti_disponibili)
        
        if 'domanda_ai' not in st.session_state or st.button("🔄 Prossima Domanda"):
            if argomento_scelto == "Mix Casuale (Tutto)":
                argomento_random = random.choice(argomenti_disponibili)
                st.session_state.domanda_ai = random.choice(st.session_state.database_domande[materia_quiz][argomento_random])
            else:
                st.session_state.domanda_ai = random.choice(st.session_state.database_domande[materia_quiz][argomento_scelto])
            
        st.info(f"**Domanda:** {st.session_state.domanda_ai['testo']}")
        st.caption(f"Ultimo punteggio: {st.session_state.domanda_ai['punteggio']}%")
        
        # --- SCELTA DELLA MODALITA' DI RISPOSTA ---
        tipo_risposta = st.radio("Scegli come rispondere:", ["⌨️ Testo Classico", "🖍️ Lavagna Interattiva (Disegno/Formule)"])
        
        risposta_testuale = ""
        immagine_da_inviare = None
        
        if tipo_risposta == "⌨️ Testo Classico":
            risposta_testuale = st.text_area("Scrivi qui la tua risposta:", height=150)
            
        elif tipo_risposta == "🖍️ Lavagna Interattiva (Disegno/Formule)":
            st.write("Usa il mouse o il pennino per disegnare le tue formule o grafici.")
            
            # --- TOOLBOX DELLA LAVAGNA ---
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

            canvas_result = st_canvas(
                fill_color="rgba(0, 0, 0, 0)",
                stroke_width=stroke_width,
                stroke_color=stroke_color,
                background_color="#FFFFFF",
                width=700,
                height=350,
                drawing_mode=drawing_mode,
                key="canvas_principale_univoco",
            )
            
            st.caption("Nota: Puoi lasciare vuoto il campo di testo se hai risposto interamente con il disegno.")
            risposta_testuale = st.text_input("Aggiungi una nota testuale opzionale al tuo disegno:", key="testo_lavagna_univoco")

        # --- INVIO AL PROFESSORE (Estrazione ultra-pulita) ---
        if st.button("Invia per la correzione"):
            
            immagine_da_inviare = None
            
            # Preleviamo l'immagine SOLO quando il pulsante viene premuto, evitando colli di bottiglia!
            if tipo_risposta == "🖍️ Lavagna Interattiva (Disegno/Formule)":
                if canvas_result is not None and canvas_result.image_data is not None:
                    try:
                        img_array = canvas_result.image_data
                        img_rgba = Image.fromarray(img_array.astype('uint8'), 'RGBA')
                        immagine_da_inviare = img_rgba.convert('RGB')
                    except Exception:
                        pass
                        
            if risposta_testuale.strip() == "" and immagine_da_inviare is None:
                st.warning("Inserisci una risposta testuale o fai un disegno sulla lavagna!")
            elif api_key:
                with st.spinner("Il professore sta analizzando il tuo elaborato... ⏳"):
                    try:
                        prompt_prof = f"""
                        Sei un professore universitario di {materia_quiz}. 
                        Valuta lo studente di biotecnologie in modo preciso e incoraggiante.
                        Domanda: "{st.session_state.domanda_ai['testo']}"
                        
                        L'utente ha risposto con del testo ("{risposta_testuale}") e/o con un'immagine allegata.
                        Valuta l'accuratezza scientifica globale, decifrando eventuali formule matematiche, strutture chimiche o grafici disegnati a mano.
                        (Se l'immagine allegata è completamente bianca/vuota e il testo è assente, fai notare che non ha fornito la risposta).
                        
                        REGOLA SUL VOTO: Un 100% si ottiene dimostrando di aver capito il meccanismo logico.
                        
                        La primissima riga DEVE contenere SOLO il voto da 0 a 100 seguito dal % (Es: 100%).
                        Poi scrivi l'Analisi e un Trucco Mnemonico.
                        """
                        risposta_finale = interroga_ai_con_fallback(prompt_prof, immagine_pill=immagine_da_inviare)
                        
                        match = re.search(r'(\d{1,3})%', risposta_finale)
                        if match:
                            voto = int(match.group(1))
                            st.session_state.domanda_ai['punteggio'] = voto
                            if voto >= 90: st.balloons()
                            
                        st.write(risposta_finale)
                    except Exception as e: 
                        st.error(f"Errore critico AI: {e}")
                        
# ==========================================
# MODULO 4: DASHBOARD MASTERY (Versione Integrale)
# ==========================================
elif modalita == "📈 Dashboard Mastery":
    st.title("📈 Dashboard a Espansione")
    st.write("Apri gli argomenti per visualizzare le domande. Clicca sui pulsanti per generare nuove domande al volo.")
    
    materia_dash = st.selectbox("Analizza la materia:", list(st.session_state.database_domande.keys()) if st.session_state.database_domande else [])
    
    if materia_dash:
        argomenti = st.session_state.database_domande[materia_dash]
        for nome_argomento, lista_domande in argomenti.items():
            with st.expander(f"📁 {nome_argomento} ({len(lista_domande)} domande)"):
                
                # --- PULSANTE MAGICO PER GENERARE ALTRE DOMANDE ---
                if st.button(f"➕ Genera 1 nuova domanda su '{nome_argomento}'", key=f"btn_{nome_argomento}"):
                    if api_key:
                        with st.spinner("Creazione in corso... ⏳"):
                            prompt_nuova = f"Sei un professore universitario. Genera UNA singola domanda d'esame complessa sulla materia '{materia_dash}', focalizzata in particolare sull'argomento '{nome_argomento}'. Restituisci SOLO il testo della domanda, senza numerazione o altro."
                            try:
                                nuova_domanda = interroga_ai_con_fallback(prompt_nuova).strip()
                                
                                if nuova_domanda:
                                    st.session_state.database_domande[materia_dash][nome_argomento].append({"testo": nuova_domanda, "punteggio": 0})
                                    st.success("Domanda aggiunta con successo!")
                                    st.rerun() 
                            except Exception as e:
                                st.error(f"Errore durante la generazione: {e}")
                    else:
                        st.error("Inserisci l'API Key nella barra laterale per usare questa funzione.")
                
                st.markdown("---")
                
                # Lista delle domande con le barre di progresso
                for idx, d in enumerate(lista_domande):
                    col_testo, col_barra = st.columns([3, 1])
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
