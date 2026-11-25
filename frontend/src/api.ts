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

export const messageErreur = (e: unknown): string => (e instanceof Error ? e.message : "Opération impossible.");
