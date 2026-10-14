import type { ReactNode } from "react";
import { Files } from "lucide-react";

export function State({ value }: { value: string }) {
  return (
    <span className={`state ${value}`}>
      <span />
      {value}
    </span>
  );
}

export function Empty({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: typeof Files;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon">
        <Icon size={32} strokeWidth={1.3} />
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
