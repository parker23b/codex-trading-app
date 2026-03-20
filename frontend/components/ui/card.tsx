import type { ReactNode } from "react";

type CardProps = {
  title: string;
  subtitle?: string;
  children: ReactNode;
  action?: ReactNode;
  className?: string;
};

export function Card({ title, subtitle, children, action, className }: CardProps) {
  return (
    <section className={`card ${className ?? ""}`.trim()}>
      <div className="card-header">
        <div>
          <h2>{title}</h2>
          {subtitle ? <p className="muted">{subtitle}</p> : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

