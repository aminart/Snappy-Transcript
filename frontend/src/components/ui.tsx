import React from "react";

/** Libellé + contrôle + aide : les ids relient le tout pour les lecteurs d'écran. */
export const Champ: React.FC<{ id: string; label: string; aide?: React.ReactNode; children: React.ReactNode }> = ({ id, label, aide, children }) => (
  <div className="flex flex-col gap-1.5">
    <label htmlFor={id} className="text-sm font-medium text-ink">{label}</label>
    {children}
    {aide && <span id={`${id}-aide`} className="text-[13px] leading-snug text-ink-muted">{aide}</span>}
  </div>
);

export const Section: React.FC<{ titre: string; children: React.ReactNode }> = ({ titre, children }) => (
  <section className="nn-card flex flex-col gap-4 p-5">
    <h2 className="m-0 text-[15px] font-bold text-ink">{titre}</h2>
    {children}
  </section>
);

export const Alerte: React.FC<{ type?: "danger" | "warning" | "success" | "info"; children: React.ReactNode }> = ({ type = "danger", children }) => {
  const couleurs = {
    danger: "border-danger bg-danger-soft text-danger-text",
    warning: "border-warning-line bg-warning-soft text-warning-text",
    success: "border-success bg-success-soft text-success-text",
    info: "border-line bg-surface-2 text-ink-body",
  }[type];
  return (
    <p role={type === "danger" ? "alert" : "status"} className={`m-0 rounded border px-4 py-3 text-sm ${couleurs}`}>{children}</p>
  );
};

export const Chiffre: React.FC<{ label: string; valeur: React.ReactNode }> = ({ label, valeur }) => (
  <div className="nn-card flex flex-col gap-1.5 p-4">
    <span className="text-[13px] text-ink-muted">{label}</span>
    <span className="text-[22px] font-bold leading-none text-ink">{valeur}</span>
  </div>
);

/** Barre de progression ; `fraction` null : durée inconnue, la barre reste vide. */
export const Progression: React.FC<{ fraction: number | null; libelle: string }> = ({ fraction, libelle }) => {
  const pct = fraction === null ? 0 : Math.max(0, Math.min(100, Math.round(fraction * 100)));
  return (
    <div className="flex flex-col gap-1.5">
      <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={fraction === null ? undefined : pct}
        aria-label={libelle} className="h-2 overflow-hidden rounded-full bg-surface-3">
        <div className="h-full rounded-full bg-primary transition-[width] duration-300" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[13px] text-ink-muted">{libelle}</span>
    </div>
  );
};

export const Verifie: React.FC<{ resultat: { valid: boolean; message: string; name?: string; missing?: string[] } | null; vide: string }> = ({ resultat, vide }) => {
  if (!resultat) return <span className="text-[13px] text-ink-muted">{vide}</span>;
  if (resultat.valid) return <span className="nn-chip nn-chip-success self-start">✓ {resultat.name ? `Modèle détecté : ${resultat.name}` : resultat.message}</span>;
  return (
    <span className="text-[13px] text-warning-text">
      {resultat.message}{resultat.missing && resultat.missing.length > 0 && ` Manquants : ${resultat.missing.join(", ")}.`}
    </span>
  );
};
