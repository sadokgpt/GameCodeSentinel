GAMECODE SENTINEL 1.4.0
=====================

OBIETTIVO
---------
Controllare ogni giorno i codici di riscatto per:
- Genshin Impact
- Aniimo
- AION 2

Il programma consulta fonti ufficiali, siti editoriali/tracker e Reddit, salva i risultati
in un database locale e cerca di evitare sia falsi positivi sia notifiche duplicate.
I codici riscattati possono essere marcati "usati" e vengono nascosti dalla vista principale.

INSTALLAZIONE RAPIDA SU WINDOWS
-------------------------------
1. Installa Python 3.11 o superiore da python.org, se non è già presente.
2. Estrai lo ZIP in una cartella che NON intendi cancellare o spostare.
3. Fai doppio clic su INSTALLA_WINDOWS.bat.
4. Verrà creato un collegamento "GameCode Sentinel" sul Desktop.
5. Apri Impostazioni nel programma per cambiare l'orario giornaliero (predefinito 08:00)
   e, se vuoi, configurare la notifica sul telefono.

NOTIFICHE
---------
Windows:
- abilitate di default.

Telefono via ntfy (opzionale):
1. Installa l'app ntfy sul telefono.
2. In GameCode Sentinel apri Impostazioni.
3. Abilita "Notifica sul telefono via ntfy".
4. Premi "Genera" per creare un topic lungo e casuale.
5. Nell'app ntfy iscriviti ESATTAMENTE allo stesso topic.
6. Premi "Prova telefono" prima di salvare.
7. Salva + attiva il controllo giornaliero.

IMPORTANTE: il topic ntfy funziona come un indirizzo segreto. Non usare nomi semplici e
non condividerlo. Il programma non salva password dei giochi né cookie di login.

COME VIENE VALUTATO UN CODICE
-----------------------------
- UFFICIALE (100): trovato in una fonte ufficiale del gioco.
- CONFERMATO (2+ fonti note) (90): presente in almeno due editori editoriali/tracker realmente indipendenti.
- RISCONTRO MISTO (80): una fonte editoriale/tracker + una fonte community.
- CONFERMATO COMMUNITY (70): almeno due fonti community distinte.
- COMMUNITY CONFERMATA (65): una segnalazione Reddit con più riscontri positivi.
- SEGNALATO (fonte nota) (60): una sola fonte editoriale/tracker.
- COMMUNITY / DA VERIFICARE (30): una sola segnalazione community.
- CONTESTATO (<=25): prevalgono riscontri negativi.

Le testate Pro Game Guides e Destructoid appartengono entrambe a GAMURS e non valgono come due editori indipendenti.
La soglia automatica predefinita è 85. In pratica il programma notifica automaticamente
solo codici ufficiali o confermati da almeno due editori/tracker realmente indipendenti,
quando il codice è stato ritrovato NEL CONTROLLO CORRENTE.
Le segnalazioni meno certe restano visibili se "Mostra da verificare" è attivo. Per le nuove installazioni è DISATTIVATO per limitare falsi positivi.

DEDUPLICAZIONE E CODICI GIÀ VISTI
---------------------------------
Ogni codice è identificato da gioco + codice normalizzato e viene salvato una sola volta.
Se la stessa stringa ricompare nei giorni successivi, il record viene aggiornato ma non
viene creato un duplicato.

Le notifiche Windows e telefono hanno stati separati: un errore su un canale non blocca
l'altro. Una volta notificato su un canale, lo stesso codice non viene rinotificato su quel
canale solo perché ricompare in seguito.

Per Aniimo viene conservata la grafia della fonte più autorevole, perché la capitalizzazione
può essere importante.

CODICI CHE SPARISCONO DALLE FONTI
---------------------------------
Un codice senza scadenza esplicita non può restare "attivo" per sempre solo perché è stato
visto una volta. Se un tracker che in precedenza lo riportava continua a essere raggiungibile
ma il codice non compare più per 3 controlli successivi, il record viene marcato internamente
come "stale" (non più rilevato) e sparisce dalla vista/notifiche. Lo storico resta nel database.

Se una fonte è temporaneamente irraggiungibile non viene contato come assenza del codice.
Le news ufficiali e Reddit non vengono usati da soli per dichiarare un codice "stale", perché
un vecchio post che esce dal feed non significa necessariamente che il codice sia scaduto.

NOVITÀ IMPORTANTI VERSIONE 1.2
------------------------------
- AION 2: niente più riconoscimento indiscriminato di parole che contengono AION2
  o di stringhe casuali vicine alla parola "code". Il coupon deve comparire in
  una istruzione esplicita di riscatto o in una lista di coupon ben identificata.
- Su AION 2 gli esempi, i segnaposto e le stringhe nelle istruzioni non sono coupon.
- Le date di scadenza non vengono dedotte da generiche date di pubblicazione.
  Per AION 2 viene letta la scadenza EU dichiarata ufficialmente, se presente.
- I codici AION 2 attivi salvati dalle versioni precedenti vengono temporaneamente
  messi in RIVERIFICA alla prima apertura. Tornano visibili quando una scansione
  conforme alle nuove regole li conferma. Si evita così di conservare codici falsi.
- Prima della prima migrazione, se il database contiene dati, il programma crea
  automaticamente una copia di sicurezza codes.before_v1.2.sqlite3 nella cartella dati.
- Il punteggio di conferma può diminuire: riflette le prove raccolte ADESSO,
  non conserva per sempre il massimo storico.
- Un codice già salvato che NON compare nella scansione corrente non genera
  nuove notifiche, anche se restava confermato nel database.
- Le segnalazioni Reddit negative non aumentano più anche il conteggio positivo;
  in thread con più codici le conferme si attribuiscono al codice menzionato.
- La schermata ha un filtro per mostrare storico, scaduti e record da riverificare.
- Le pagine challenge anti-bot e i reindirizzamenti a domini diversi vengono
  trattati come errori, non come prove dell'assenza di un codice.

COME AGGIORNARE DALLA 1.1
------------------------
1. Estrai questo ZIP in una nuova cartella permanente.
2. Esegui INSTALLA_WINDOWS.bat; il collegamento Desktop e i task verranno aggiornati.
3. Apri il programma e premi "Controlla ora".
4. I vecchi record AION 2 non ancora riconfermati sono visibili attivando
   "Mostra storico/scaduti" (e "Mostra usati" se vuoi includerli).
5. I dati di codici già usati e le notifiche già inviate restano salvati.

NOTA: non è possibile verificare automaticamente il riscatto sul proprio account.
La conferma del codice significa conferma della fonte, non risposta live del server di gioco.

FONTI INCLUSE
-------------
Genshin Impact:
- HoYoverse News
- Pocket Tactics
- Destructoid
- Reddit r/Genshin_Impact
- Reddit r/GenshinImpact

Aniimo:
- Aniimo News ufficiali
- Pocket Tactics
- Pocket Gamer
- Aniimo Wiki
- Reddit r/AniimoGuide

AION 2:
- PURPLE Lounge / AION 2 official
- Steam: annunci ufficiali AION 2
- AION 2 / PLAYNC notice ufficiali
- NCSOFT News
- Pro Game Guides
- Destructoid
- Reddit r/Aion2

Le fonti possono cambiare struttura o bloccare richieste automatiche. Il programma usa timeout,
retry limitati e continua con le altre fonti quando una singola fonte fallisce.

RISCATTO
--------
Genshin Impact:
- "Riscatta / istruzioni" apre la pagina ufficiale HoYoverse e copia il codice negli appunti.

Aniimo:
- il codice viene copiato negli appunti e il programma mostra il percorso di riscatto nel gioco.

AION 2:
- il codice viene copiato negli appunti e il programma mostra il percorso di registrazione coupon.

Dopo il riscatto premi sempre "Segna come usato". Il programma non effettua login automatici
agli account e quindi non può sapere in modo affidabile se TU hai già riscattato un codice.

CONTROLLO AUTOMATICO
--------------------
Il controllo giornaliero viene creato con l'Utilità di pianificazione di Windows tramite
schtasks. Viene creato anche, quando Windows lo consente, un controllo di recupero all'accesso:
se il PC era spento o in sospensione all'orario previsto, il controllo viene rifatto al login.
La deduplicazione evita che questo generi doppie notifiche. Se apri il programma manualmente,
viene comunque avviato un nuovo controllo subito dopo l'apertura.

DATABASE E LOG
--------------
Database:
%LOCALAPPDATA%\GameCodeSentinel\codes.db

Configurazione:
%LOCALAPPDATA%\GameCodeSentinel\config.json

Log:
%LOCALAPPDATA%\GameCodeSentinel\app.log

Nel database vengono conservati:
- gioco e codice
- ricompensa
- stato e livello di verifica
- fonti e numero di fonti
- prima/ultima rilevazione
- scadenza, quando rilevabile
- stato usato
- stato notifica Windows/telefono
- conteggio delle assenze successive dai tracker

CREARE UN .EXE
--------------
Dopo l'installazione puoi eseguire CREA_EXE_WINDOWS.bat.
L'eseguibile verrà creato in:
dist\GameCodeSentinel.exe

Il batch prova anche ad aggiornare l'attività pianificata affinché punti direttamente all'EXE.

LIMITI IMPORTANTI
-----------------
- Nessun sistema esterno permette al tool di sapere universalmente e senza login se un codice
  è stato già riscattato sul tuo specifico account: per questo esiste "Segna come usato".
- Un codice trovato su Reddit non viene considerato automaticamente affidabile.
- La validità assoluta può essere confermata solo dal server del gioco al momento del riscatto.
- Eventuali codici regionali possono richiedere un controllo manuale della fonte prima del riscatto.
- I controlli automatizzati non sostituiscono la verifica all’interno del client di gioco.
- La versione ZIP contiene script Python per Windows; NON contiene un .exe già compilato.
  Puoi crearlo sul tuo PC con CREA_EXE_WINDOWS.bat.
- I test automatici sono stati eseguiti in ambiente Python; la GUI e il Task Scheduler
  Windows richiedono una prova sulla macchina finale.
- Per eseguire i test: python -m pip install pytest ; python -m pytest -q tests

GESTIONE MULTIPLA DEI CODICI (1.3.3)
-----------------------------------
Ctrl+clic seleziona singole righe; Maiusc+clic seleziona intervalli.
Ctrl+A o Seleziona tutti visibili seleziona tutte le righe attualmente mostrate.
Segna usati nasconde i codici senza cancellarli.
Mostra usati + Ripristina usati permette di annullare la marcatura.
I codici Non valido non vengono ripristinati automaticamente.


VERSIONE 1.4.0 - NOVITA'
----------------------
- Ricerca codice/ricompensa nella finestra principale; clic sulle colonne per ordinare.
- Colonna Ultima vista e finestra Stato fonti con errori e tempi per ogni fonte.
- Scansioni parallele limitate con protezione dai controlli simultanei.
- Controllo di pagine tracker vuote o non riconoscibili per ridurre falsi scaduti.
- Backup SQLite automatici ogni 24 ore, mantenendo fino a 7 snapshot consistenti.
- Pulsante Backup per creare una copia; da terminale: python app.py --backup.
- Notifiche con controllo anti-duplicazione fra istanze e verifica dello stato corrente.
- Scadenze senza ora interpretate fino a fine giornata e AION EU confrontato su ora italiana.
- Build Windows v1.4.0 e checksum pubblicati in Actions; workflow di release su tag.

Il programma non elimina i codici marcati usati. Prima di aggiornare fai sempre una
copia di %LOCALAPPDATA%\\GameCodeSentinel\\codes.db o usa il nuovo pulsante Backup.
La funzione di ripristino automatico con pulsante non e' ancora disponibile.
