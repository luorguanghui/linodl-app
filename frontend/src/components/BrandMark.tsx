interface BrandMarkProps {
  title?: string;
  className?: string;
}

export function BrandMark({ title, className }: BrandMarkProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 1024 1024"
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : "true"}
    >
      {title ? <title>{title}</title> : null}
      <path
        className="brand-mark__cover"
        d="M248 112h568v800H248c-80 0-144-64-144-144V256c0-80 64-144 144-144Z"
      />
      <path
        className="brand-mark__page"
        d="M248 160h568v144H248c-40 0-72-32-72-72s32-72 72-72Z"
      />
      <path
        className="brand-mark__bookmark"
        d="M432 160h160v512l-80 96-80-96V160Z"
      />
    </svg>
  );
}
