import Link from "next/link";

import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

/** Cartão de indicador do admin (número + legenda), opcionalmente clicável. */
export function Indicador({
  titulo,
  valor,
  legenda,
  icone: Icone,
  carregando,
  href,
  tom,
}: {
  titulo: string;
  valor: React.ReactNode;
  legenda?: React.ReactNode;
  icone: React.ComponentType<{ className?: string }>;
  carregando?: boolean;
  href?: string;
  tom?: "danger" | "warning" | "success";
}) {
  const corpo = (
    <>
      <div className="flex items-start justify-between gap-2">
        <p className="text-[13px] font-medium text-muted-foreground">{titulo}</p>
        <div
          className={cn(
            "grid size-8 place-items-center rounded-lg bg-brand/10 text-navy dark:text-brand",
            tom === "danger" && "bg-danger/10 text-danger-ink dark:text-danger-ink",
            tom === "warning" && "bg-warning/12 text-warning-ink dark:text-warning-ink",
            tom === "success" && "bg-success/10 text-success-ink dark:text-success-ink",
          )}
        >
          <Icone className="size-4" />
        </div>
      </div>
      {carregando ? (
        <Skeleton className="mt-3 h-8 w-24" />
      ) : (
        <p className="num mt-2 truncate text-[22px] leading-tight font-semibold tracking-tight sm:text-[26px]">{valor}</p>
      )}
      {legenda && <p className="mt-1.5 truncate text-xs text-muted-foreground">{legenda}</p>}
    </>
  );
  const cls = "card-surface block p-4";
  return href ? (
    <Link href={href} className={cn(cls, "transition-colors hover:border-brand/50")}>
      {corpo}
    </Link>
  ) : (
    <div className={cls}>{corpo}</div>
  );
}
