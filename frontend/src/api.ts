/** Appel JSON : en cas d'erreur, lève un Error dont le message est celui du serveur (en français). */
export async function api<T>(url: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const { json, ...reste } = init;
  const reponse = await fetch(url, {
    ...reste,
    headers: json !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: json !== undefined ? JSON.stringify(json) : reste.body,
  });
  if (!reponse.ok) {
    let message = `Erreur ${reponse.status}`;
    try {
      const donnees = await reponse.json();
      if (typeof donnees.detail === "string") message = donnees.detail;
      else if (Array.isArray(donnees.detail)) message = "Valeur invalide : " + donnees.detail.map((d: { loc?: string[] }) => d.loc?.slice(-1)[0]).join(", ");
    } catch { /* corps vide : on garde le code */ }
    throw new Error(message);
  }
  return reponse.json() as Promise<T>;
}

/**
 * Envoie un fichier au serveur local (même PC : simple copie, rien ne sort sur le réseau), avec sa progression.
 * XMLHttpRequest plutôt que fetch : fetch ne donne pas l'avancement d'un envoi.
 */
export function envoyerFichier(fichier: File, progression: (fraction: number) => void, signal?: AbortSignal): Promise<string> {
  return new Promise((resoudre, rejeter) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api/upload?name=${encodeURIComponent(fichier.name)}`);
    xhr.upload.onprogress = (e) => { if (e.lengthComputable) progression(e.loaded / e.total); };
    xhr.onload = () => {
      let donnees: { upload_id?: string; detail?: unknown } = {};
      try { donnees = JSON.parse(xhr.responseText); } catch { /* réponse vide */ }
      if (xhr.status >= 200 && xhr.status < 300 && donnees.upload_id) resoudre(donnees.upload_id);
      else rejeter(new Error(typeof donnees.detail === "string" ? donnees.detail : `Envoi impossible (erreur ${xhr.status}).`));
    };
    xhr.onerror = () => rejeter(new Error("Envoi du fichier interrompu."));
    xhr.onabort = () => rejeter(new Error("Envoi annulé."));
    signal?.addEventListener("abort", () => xhr.abort());
    xhr.send(fichier);
  });
}

export const messageErreur = (e: unknown): string => (e instanceof Error ? e.message : "Opération impossible.");
