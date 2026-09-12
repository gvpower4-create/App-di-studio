import streamlit as st
import google.generativeai as genai
import random
import PyPDF2
import re
import json

# --- COSTANTI E CONFIGURAZIONI ---
NOME_MODELLO = 'gemini-3.6-flash'

st.set_page_config(page_title="Nexus Study App", page_icon="🧬", layout="wide")

# --- INIZIALIZZAZIONE VUOTA PER OGNI UTENTE ---
# Ogni utente che apre il sito parte con un database immacolato
if 'database_domande' not in st.session_state:
    st.session_state.database_domande = {}

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

# 1. Pulsante per SCARICARE i progressi
dati_json = json.dumps(st.session_state.database_domande, indent=4)
st.sidebar.download_button(
    label="⬇️ Scarica il mio Profilo",
    data=dati_json,
    file_name="Mio_Profilo_Nexus.json",
    mime="application/json"
)

# 2. Pulsante per CARICARE i progressi precedenti
file_profilo = st.sidebar.file_uploader("⬆️ Carica il tuo Profilo", type="json")
if file_profilo is not None:
    if 'profilo_caricato' not in st.session_state:
        st.session_state.database_domande = json.load(file_profilo)
        st.session_state.profilo_caricato = True
        st.sidebar.success("Profilo ripristinato con successo!")
        st.rerun()

st.sidebar.markdown("---")
modalita = st.sidebar.radio("Navigazione:", ["🏠 Home & Statistiche", "⚙️ Aggiungi PDF", "🎙️ Simulazione Esame", "📈 Dashboard Mastery"])

# ==========================================
# MODULO 1: HOME & STATISTICHE
# ==========================================
if modalita == "🏠 Home & Statistiche":
    st.title("🏠 Il tuo Ecosistema di Studio")
    
    if not st.session_state.database_domande:
        st.info("L'ambiente è vuoto. Carica il tuo file Profilo dalla barra laterale o vai su 'Aggiungi PDF' per iniziare!")
    else:
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
                    
                    modello = genai.GenerativeModel(NOME_MODELLO)
                    prompt = f"""
                    Agisci come professore di {materia_target}. Leggi queste dispense: "{testo_estratto}"
                    
                    1. Identifica i macro-argomenti.
                    2. Per OGNI macro-argomento, genera da 3 a 5 domande per un esame {tipo_esame}.
                    
                    DEVI RISPONDERE ESATTAMENTE CON QUESTO FORMATO:
                    ### ARGOMENTO: [Nome]
                    - [Domanda 1]
                    - [Domanda 2]
                    """
                    risposta_ai = modello.generate_content(prompt)
                    
                    if materia_target not in st.session_state.database_domande:
                        st.session_state.database_domande[materia_target] = {}
                    
                    righe = risposta_ai.text.strip().split('\n')
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
                    st.error(f"Errore: {e}")

# ==========================================
# MODULO 3: SIMULAZIONE
# ==========================================
elif modalita == "🎙️ Simulazione Esame":
    st.title("🎙️ Simulazione Mirata")
    
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
        
        risposta_utente = st.text_area("Scrivi qui la tua risposta:", height=200)
        
        if st.button("Invia per la correzione"):
            if risposta_utente.strip() == "":
                st.warning("Scrivi una risposta!")
            elif api_key:
                with st.spinner("Valutazione... ⏳"):
                    try:
                        modello = genai.GenerativeModel(NOME_MODELLO)
                        prompt = f"""
                        Agisci come professore universitario di {materia_quiz}. 
                        Domanda: "{st.session_state.domanda_ai['testo']}"
                        Risposta: "{risposta_utente}"
                        
                        REGOLA SULLE FORMULE: Non penalizzare l'assenza di formule matematiche scritte, accetta descrizioni discorsive.
                        REGOLA SUL VOTO: Un 100% si ottiene capendo la logica.
                        
                        La primissima riga DEVE contenere SOLO un numero da 0 a 100 seguito dal % (Es: 100%).
                        Poi fornisci Analisi e Trucco Mnemonico.
                        """
                        risposta_ai = modello.generate_content(prompt)
                        
                        match = re.search(r'(\d{1,3})%', risposta_ai.text)
                        if match:
                            voto = int(match.group(1))
                            st.session_state.domanda_ai['punteggio'] = voto
                            if voto >= 90: st.balloons()
                            
                        st.write(risposta_ai.text)
                    except Exception as e: st.error(f"Errore AI: {e}")

# ==========================================
# MODULO 4: DASHBOARD MASTERY
# ==========================================
elif modalita == "📈 Dashboard Mastery":
    st.title("📈 Dashboard a Espansione")
    
    materia_dash = st.selectbox("Analizza la materia:", list(st.session_state.database_domande.keys()) if st.session_state.database_domande else [])
    
    if materia_dash:
        argomenti = st.session_state.database_domande[materia_dash]
        for nome_argomento, lista_domande in argomenti.items():
            with st.expander(f"📁 {nome_argomento} ({len(lista_domande)} domande)"):
                
                if st.button(f"➕ Genera 1 nuova domanda", key=f"btn_{nome_argomento}"):
                    if api_key:
                        with st.spinner("Creazione in corso... ⏳"):
                            modello = genai.GenerativeModel(NOME_MODELLO)
                            prompt_nuova = f"Genera UNA singola domanda complessa su '{materia_dash}', focalizzata su '{nome_argomento}'. Restituisci SOLO il testo della domanda."
                            try:
                                risp = modello.generate_content(prompt_nuova)
                                nuova_domanda = risp.text.strip()
                                if nuova_domanda:
                                    st.session_state.database_domande[materia_dash][nome_argomento].append({"testo": nuova_domanda, "punteggio": 0})
                                    st.success("Domanda aggiunta con successo!")
                                    st.rerun()
                            except Exception as e: st.error(f"Errore: {e}")
                    else:
                        st.error("Inserisci l'API Key.")
                
                st.markdown("---")
                for idx, d in enumerate(lista_domande):
                    col_testo, col_barra = st.columns([3, 1])
                    with col_testo:
                        st.write(f"**{idx + 1}.** {d['testo']}")
                    with col_barra:
                        st.progress(d['punteggio'] / 100)
                        if d['punteggio'] == 100: st.success("100%")
                        elif d['punteggio'] >= 60: st.warning(f"{d['punteggio']}%")
                        else: st.error(f"{d['punteggio']}%")
