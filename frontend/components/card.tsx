import type { ReactNode } from "react";

type CardProps = {
  title: string;
  subtitle?: string;
  children: ReactNode;
  action?: ReactNode;
};

export function Card({ title, subtitle, children, action }: CardProps) {
  return (
    <section className="card">
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
