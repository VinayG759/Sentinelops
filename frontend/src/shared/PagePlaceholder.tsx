/** Temporary page body until the feature's phase lands. Says what will be here and when. */
export function PagePlaceholder({ title, arrives }: { title: string; arrives: string }) {
  return (
    <div>
      <h1 className="text-lg font-semibold tracking-tight">{title}</h1>
      <div className="mt-6 rounded-lg border border-dashed p-10 text-center text-muted-foreground">
        Not built yet — arrives in {arrives}.
      </div>
    </div>
  )
}
