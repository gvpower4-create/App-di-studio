import streamlit as st
import google.generativeai as genai
import random
import PyPDF2
import re
import json
import numpy as np
from PIL import Image
from streamlit_drawable_canvas import st_canvas # La nuova lavagna!

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

# --- FUNZIONE MOTORE IA (ORA MULTIMODALE: LEGGE ANCHE IMMAGINI) ---
def interroga_ai_con_fallback(prompt_testo, immagine_pill=None):
    """Prova i modelli in sequenza. Se c'è un'immagine, la invia insieme al testo."""
    for nome_modello in LISTA_MODELLI:
        try:
            modello = genai.GenerativeModel(nome_modello)
            # Se l'utente ha disegnato qualcosa, invia testo + immagine
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

st.sidebar.markdown("---")
st.sidebar.subheader("💾 Il tuo Profilo di Studio")

dati_json = json.dumps(st.session_state.database_domande, indent=4)
st.sidebar.download_button(
    label="⬇️ Scarica Profilo",
    data=dati_json,
    file_name="Mio_Profilo_Nexus.json",
    mime="application/json"
)

file_profilo = st.sidebar.file_uploader("⬆️ Carica Profilo", type="json")
if file_profilo is not None:
    if 'profilo_caricato' not in st.session_state:
        st.session_state.database_domande = json.load(file_profilo)
        st.session_state.profilo_caricato = True
        st.sidebar.success("Profilo ripristinato con successo!")
        st.rerun()

st.sidebar.markdown("---")
modalita = st.sidebar.radio("Navigazione:", ["🏠 Home & Istruzioni", "⚙️ Aggiungi PDF", "🎙️ Simulazione Esame", "📈 Dashboard Mastery"])

# ==========================================
# MODULO 1: HOME E MODULO 2: PDF (Semplificati per leggibilità)
# ==========================================
if modalita == "🏠 Home & Istruzioni":
    st.title("🏠 Il tuo Ecosistema di Studio")
    if not st.session_state.database_domande:
        st.info("Benvenuto! Usa il menu laterale per caricare il tuo profilo o vai su Aggiungi PDF.")
    else:
        for materia, argomenti in st.session_state.database_domande.items():
            st.markdown(f"### 🧬 {materia}")
            st.caption(f"{len(argomenti)} Argomenti estratti.")
            st.markdown("---")

elif modalita == "⚙️ Aggiungi PDF":
    st.title("⚙️ Estrazione Massiva")
    materia_target = st.text_input("Nome Materia:")
    tipo_esame = st.radio("Tipo di esame:", ["Orale", "Scritto"])
    file_pdf = st.file_uploader("Carica PDF", type="pdf")
    
    if st.button("Genera Domande"):
        if api_key and materia_target and file_pdf:
            with st.spinner("Estrazione in corso... ⏳"):
                try:
                    lettore = PyPDF2.PdfReader(file_pdf)
                    testo = "".join([p.extract_text() for p in lettore.pages])
                    prompt = f"Professore di {materia_target}. Leggi: '{testo}'. Genera domande. FORMATO:\n### ARGOMENTO: [Nome]\n- [Domanda]"
                    risposta = interroga_ai_con_fallback(prompt)
                    
                    if materia_target not in st.session_state.database_domande:
                        st.session_state.database_domande[materia_target] = {}
                        
                    for riga in risposta.strip().split('\n'):
                        riga = riga.strip()
                        if riga.startswith("### ARGOMENTO:"):
                            arg = riga.replace("### ARGOMENTO:", "").strip()
                            if arg not in st.session_state.database_domande[materia_target]:
                                st.session_state.database_domande[materia_target][arg] = []
                        elif riga.startswith("- "):
                            domanda = riga.replace("- ", "").strip()
                            st.session_state.database_domande[materia_target][arg].append({"testo": domanda, "punteggio": 0})
                    st.success("✅ Domande aggiunte!")
                except Exception as e: st.error(f"Errore: {e}")

# ==========================================
# MODULO 3: SIMULAZIONE (IL NUOVO MOTORE MULTIMODALE)
# ==========================================
elif modalita == "🎙️ Simulazione Esame":
    st.title("🎙️ Simulazione Interattiva")
    
    materia_quiz = st.selectbox("Scegli la materia:", list(st.session_state.database_domande.keys()) if st.session_state.database_domande else [])
    
    if not materia_quiz:
        st.warning("Aggiungi una materia o carica il profilo.")
    else:
        argomenti_disponibili = list(st.session_state.database_domande[materia_quiz].keys())
        argomento_scelto = st.selectbox("Argomento:", ["Mix Casuale"] + argomenti_disponibili)
        
        if 'domanda_ai' not in st.session_state or st.button("🔄 Prossima Domanda"):
            if argomento_scelto == "Mix Casuale":
                st.session_state.domanda_ai = random.choice(st.session_state.database_domande[materia_quiz][random.choice(argomenti_disponibili)])
            else:
                st.session_state.domanda_ai = random.choice(st.session_state.database_domande[materia_quiz][argomento_scelto])
            
        st.info(f"**Domanda:** {st.session_state.domanda_ai['testo']}")
        st.caption(f"Ultimo punteggio: {st.session_state.domanda_ai['punteggio']}%")
        
        # --- SCELTA DELLA MODALITA' DI RISPOSTA ---
        tipo_risposta = st.radio("Scegli come rispondere:", ["⌨️ Testo Classico", "🖍️ Lavagna Interattiva (Disegno/Formule)"])
        
        risposta_testuale = ""
        immagine_da_inviare = None
        
        if tipo_risposta == "⌨️ Testo Classico":
            risposta_testuale = st.text_area("Scrivi qui:", height=150)
            
        elif tipo_risposta == "🖍️ Lavagna Interattiva (Disegno/Formule)":
            st.write("Usa il mouse, il dito o il pennino per disegnare grafici, formule o scrivere a mano.")
            
            # Parametri della lavagna
            stroke_width = st.slider("Spessore tratto:", 1, 10, 3)
            
            # Creazione effettiva della lavagna a schermo
            canvas_result = st_canvas(
                fill_color="rgba(255, 255, 255, 0)",
                stroke_width=stroke_width,
                stroke_color="#000000", # Tratto nero
                background_color="#FFFFFF", # Sfondo bianco tipo foglio di carta
                height=400,
                drawing_mode="freedraw",
                key="canvas",
            )
            
            st.caption("Nota: Se scrivi sulla lavagna, puoi lasciare vuoto il campo di testo qui sotto.")
            risposta_testuale = st.text_input("Aggiungi una nota testuale opzionale al tuo disegno:")
            
            # Se la lavagna contiene dati (l'utente ha disegnato)
            if canvas_result.image_data is not None:
                # La lavagna produce una matrice numerica (Numpy Array). La convertiamo in Immagine per l'AI
                immagine_grezza = canvas_result.image_data
                immagine_convertita = Image.fromarray(immagine_grezza.astype('uint8'), 'RGBA')
                # Togliamo la trasparenza per farla leggere meglio al Prof virtuale
                immagine_da_inviare = immagine_convertita.convert('RGB')

        # --- INVIO AL PROFESSORE ---
        if st.button("Invia per la correzione"):
            if risposta_testuale.strip() == "" and immagine_da_inviare is None:
                st.warning("Inserisci una risposta testuale o un disegno!")
            elif api_key:
                with st.spinner("Il professore sta correggendo... ⏳"):
                    try:
                        prompt_prof = f"""
                        Sei un professore universitario di {materia_quiz}. 
                        Domanda: "{st.session_state.domanda_ai['testo']}"
                        
                        L'utente potrebbe aver risposto con testo ("{risposta_testuale}") e/o con un'immagine allegata (disegno a mano, grafici, formule matematiche).
                        Valuta l'accuratezza scientifica della risposta complessiva.
                        
                        La primissima riga DEVE contenere SOLO il voto da 0 a 100 seguito dal % (Es: 100%).
                        Poi scrivi l'Analisi e un Trucco Mnemonico.
                        """
                        # Passiamo sia il testo che l'immagine alla nostra funzione a cascata!
                        risposta_finale = interroga_ai_con_fallback(prompt_prof, immagine_pill=immagine_da_inviare)
                        
                        match = re.search(r'(\d{1,3})%', risposta_finale)
                        if match:
                            voto = int(match.group(1))
                            st.session_state.domanda_ai['punteggio'] = voto
                            if voto >= 90: st.balloons()
                            
                        st.write(risposta_finale)
                    except Exception as e: st.error(f"Errore critico: {e}")

# ==========================================
# MODULO 4: DASHBOARD MASTERY (Semplificato per leggibilità)
# ==========================================
elif modalita == "📈 Dashboard Mastery":
    st.title("📈 Dashboard")
    materia_dash = st.selectbox("Materia:", list(st.session_state.database_domande.keys()) if st.session_state.database_domande else [])
    if materia_dash:
        for arg, domande in st.session_state.database_domande[materia_dash].items():
            with st.expander(f"📁 {arg}"):
                for d in domande:
                    st.write(f"**{d['testo']}** - {d['punteggio']}%")
