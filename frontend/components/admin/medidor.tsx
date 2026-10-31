import { numero } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Barra de uso contra o limite do plano (limite null = ilimitado). */
export function Medidor({
  rotulo,
  usado,
  limite,
  compacto,
}: {
  rotulo?: string;
  usado: number | null | undefined;
  limite: number | null | undefined;
  compacto?: boolean;
}) {
  const u = usado ?? 0;
  const pct = limite ? Math.min(100, (u / limite) * 100) : 0;
  return (
    <div className={compacto ? "min-w-28" : undefined}>
      <div className={cn("mb-1 flex justify-between gap-2", compacto ? "text-xs" : "text-sm")}>
        {rotulo && <span>{rotulo}</span>}
        <span className="num text-muted-foreground">
          <span className="text-foreground">{usado == null ? "—" : numero(u)}</span> / {limite ? numero(limite) : "∞"}
        </span>
      </div>
      <div className={cn("overflow-hidden rounded-full bg-muted", compacto ? "h-1.5" : "h-2")}>
        <div
          className={cn("h-full rounded-full", pct >= 100 ? "bg-danger" : pct >= 80 ? "bg-warning" : "bg-brand")}
          style={{ width: `${limite ? pct : 4}%` }}
        />
      </div>
    </div>
  );
}
