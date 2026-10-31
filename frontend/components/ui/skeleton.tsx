import { cn } from "cn"

/** Esqueleto de carregamento com brilho deslizante (padrão MayaFit). */
function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      aria-hidden
      className={cn("skeleton-shimmer animate-shimmer rounded-md bg-muted", className)}
      {...props}
    />
  )
}

export { Skeleton }
