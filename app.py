import streamlit as st
import google.generativeai as genai
import random
import PyPDF2
import re
import json
import os

# --- COSTANTI E CONFIGURAZIONI ---
NOME_MODELLO = 'gemini-3.6-flash'
FILE_DATI = 'database_nexus.json'

st.set_page_config(page_title="Nexus Study App", page_icon="🧬", layout="wide")

# --- FUNZIONI DI MEMORIA PERMANENTE ---
def carica_dati():
    if os.path.exists(FILE_DATI):
        with open(FILE_DATI, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def salva_dati(dati):
    with open(FILE_DATI, 'w', encoding='utf-8') as f:
        json.dump(dati, f, indent=4, ensure_ascii=False)

if 'database_domande' not in st.session_state:
    st.session_state.database_domande = carica_dati()

# --- BARRA LATERALE ---
st.sidebar.title("🧬 Nexus Ecosistema")

# Cerca la chiave nella cassaforte segreta; se non c'è, lascia il campo vuoto
chiave_salvata = st.secrets.get("GOOGLE_API_KEY", "")

# Il box di testo si pre-compilerà da solo se la chiave è nella cassaforte
api_key = st.sidebar.text_input("Inserisci la tua API Key:", value=chiave_salvata, type="password")

if api_key:
    genai.configure(api_key=api_key)
else:
    st.sidebar.warning("Inserisci la chiave per attivare l'AI.")
st.sidebar.markdown("---")
# Abbiamo cambiato il nome della prima modalità
modalita = st.sidebar.radio("Navigazione:", ["🏠 Home & Statistiche", "⚙️ Aggiungi PDF", "🎙️ Simulazione Esame", "📈 Dashboard Mastery"])

# ==========================================
# MODULO 1: HOME & STATISTICHE (Rinnovato)
# ==========================================
if modalita == "🏠 Home & Statistiche":
    st.title("🏠 Il tuo Ecosistema di Studio")
    st.write("Panoramica del materiale immagazzinato e pronto per la simulazione.")
    
    if not st.session_state.database_domande:
        st.info("Il database è vuoto. Vai su 'Aggiungi PDF' per iniziare a studiare!")
    else:
        # Calcolo delle statistiche
        tot_materie = len(st.session_state.database_domande)
        tot_argomenti = sum(len(argomenti) for argomenti in st.session_state.database_domande.values())
        tot_domande = sum(len(domande) for argomenti in st.session_state.database_domande.values() for domande in argomenti.values())
        
        # UI Grafica a 3 colonne per le metriche
        col1, col2, col3 = st.columns(3)
        col1.metric("📚 Materie Inserite", tot_materie)
        col2.metric("📁 Argomenti Estrapolati", tot_argomenti)
        col3.metric("❓ Domande Generate", tot_domande)
        
        st.markdown("---")
        st.subheader("Dettaglio Materie")
        
        # Mostriamo le materie come "schede" visive
        for materia, argomenti in st.session_state.database_domande.items():
            with st.container():
                st.markdown(f"### 🧬 {materia}")
                domande_materia = sum(len(d) for d in argomenti.values())
                st.caption(f"{len(argomenti)} Argomenti | {domande_materia} Domande totali")
                
                # Mostriamo i "tag" degli argomenti presenti in quella materia
                tags = " | ".join([f"*{arg}*" for arg in argomenti.keys()])
                st.write(tags)
                st.markdown("---")

# ==========================================
# MODULO 2: LETTURA PDF (Invariato graficamente)
# ==========================================
elif modalita == "⚙️ Aggiungi PDF":
    st.title("⚙️ Estrazione Massiva per Argomenti")
    st.write("L'AI analizzerà il PDF, individuerà i macro-argomenti e creerà decine di domande categorizzate.")
    
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
                    
                    salva_dati(st.session_state.database_domande)
                    st.success(f"✅ Generate {totale_domande} domande. Dati salvati.")
                except Exception as e:
                    st.error(f"Errore: {e}")

# ==========================================
# MODULO 3: SIMULAZIONE (Prompt Professore Aggiornato)
# ==========================================
elif modalita == "🎙️ Simulazione Esame":
    st.title("🎙️ Simulazione Mirata")
    
    materia_quiz = st.selectbox("Scegli la materia:", list(st.session_state.database_domande.keys()) if st.session_state.database_domande else [])
    
    if not materia_quiz:
        st.warning("Aggiungi prima una materia.")
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
                        # --- ECCO IL PROMPT TARATO PER IL 30 E LODE REALISTICO ---
                        prompt = f"""
                        Agisci come un professore universitario di {materia_quiz}. Stai valutando un'interrogazione.
                        Domanda: "{st.session_state.domanda_ai['testo']}"
                        Risposta studente: "{risposta_utente}"
                        
                        REGOLA SULLE FORMULE: L'esame è al computer. NON penalizzare lo studente se non scrive formule matematiche, reazioni chimiche o equazioni in formato esatto. Accetta descrizioni a parole delle formule o dei processi.
                        REGOLA SUL VOTO (Sii realista): Un 30 e lode (100%) si ottiene capendo la logica e i concetti chiave, non richiedendo la perfezione di un libro di testo. Se il concetto e il ragionamento ci sono, assegna tranquillamente 100%. Sii incoraggiante.
                        
                        REGOLA FONDAMENTALE: La primissima riga deve contenere SOLO un numero da 0 a 100 seguito dal % (Es: 100%).
                        Poi fornisci: 
                        1. Analisi (cosa va bene, cosa manca). 
                        2. Trucco Mnemonico.
                        """
                        risposta_ai = modello.generate_content(prompt)
                        
                        match = re.search(r'(\d{1,3})%', risposta_ai.text)
                        if match:
                            voto = int(match.group(1))
                            st.session_state.domanda_ai['punteggio'] = voto
                            salva_dati(st.session_state.database_domande)
                            if voto >= 90: st.balloons()
                            
                        st.write(risposta_ai.text)
                    except Exception as e: st.error(f"Errore AI: {e}")

# ==========================================
# MODULO 4: DASHBOARD MASTERY (Aggiunta Generazione Dinamica)
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
                            modello = genai.GenerativeModel(NOME_MODELLO)
                            prompt_nuova = f"Sei un professore universitario. Genera UNA singola domanda d'esame complessa sulla materia '{materia_dash}', focalizzata in particolare sull'argomento '{nome_argomento}'. Restituisci SOLO il testo della domanda, senza numerazione o altro."
                            try:
                                risp = modello.generate_content(prompt_nuova)
                                nuova_domanda = risp.text.strip()
                                # Controlla che non sia una domanda vuota
                                if nuova_domanda:
                                    st.session_state.database_domande[materia_dash][nome_argomento].append({"testo": nuova_domanda, "punteggio": 0})
                                    salva_dati(st.session_state.database_domande)
                                    st.success("Domanda aggiunta con successo!")
                                    st.rerun() # Ricarica l'interfaccia per mostrare subito la nuova domanda
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