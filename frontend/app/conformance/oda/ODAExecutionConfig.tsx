"use client";
import { Card, Button, Input } from "../../components/ui";

// Mirrors backend ODACTKJobReq / ODACTKConfig (backend/main.py) exactly.
export interface CtkFormValue {
  release_name: string;
  namespace: string;
  company_name: string;
  product_name: string;
  product_url: string;
  product_version: string;
  authorization: string;          // transient secret — never persisted, cleared after submit
  reject_unauthorized: boolean;
  run_exposed_optional: boolean;
  run_dependent_optional: boolean;
  run_security_optional: boolean;
}

export const EMPTY_CONFIG: CtkFormValue = {
  release_name: "", namespace: "components",
  company_name: "", product_name: "", product_url: "", product_version: "",
  authorization: "", reject_unauthorized: false,
  run_exposed_optional: false, run_dependent_optional: false, run_security_optional: false,
};

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-gray-600 dark:text-slate-300">{label}</span>
      <div className="mt-1">{children}</div>
      {hint && <span className="text-[11px] text-gray-400 dark:text-slate-500">{hint}</span>}
    </label>
  );
}

function Check({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-slate-300 cursor-pointer">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)}
        className="w-4 h-4 rounded border-gray-300 dark:border-slate-600 text-red-600 focus:ring-red-500" />
      {label}
    </label>
  );
}

export default function ODAExecutionConfig({
  value, onChange, onValidate, validating, running, canValidate, authArmed, onReplaceAuth,
}: {
  value: CtkFormValue;
  onChange: (v: CtkFormValue) => void;
  onValidate: () => void;
  validating: boolean;
  running: boolean;
  canValidate: boolean;
  authArmed?: boolean;          // secret already captured — never re-render its value
  onReplaceAuth?: () => void;   // clear the captured secret and re-show the input
}) {
  const set = (patch: Partial<CtkFormValue>) => onChange({ ...value, ...patch });
  const busy = validating || running;

  return (
    <Card className="p-5">
      <h3 className="text-sm font-semibold text-gray-800 dark:text-slate-100">Execution configuration</h3>
      <p className="text-xs text-gray-400 dark:text-slate-500 mt-0.5 mb-4">
        Points the TM Forum Component CTK at your deployed component. These map directly to the framework’s CHANGE_ME.json.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5">
        <Field label="Helm release name" hint="The deployed component’s Helm release">
          <Input value={value.release_name} onChange={(e) => set({ release_name: e.target.value })} placeholder="rc-1" />
        </Field>
        <Field label="Kubernetes namespace">
          <Input value={value.namespace} onChange={(e) => set({ namespace: e.target.value })} placeholder="components" />
        </Field>
        <Field label="Company name">
          <Input value={value.company_name} onChange={(e) => set({ company_name: e.target.value })} placeholder="Acme Networks" />
        </Field>
        <Field label="Product name">
          <Input value={value.product_name} onChange={(e) => set({ product_name: e.target.value })} placeholder="Fault Manager" />
        </Field>
        <Field label="Product URL">
          <Input value={value.product_url} onChange={(e) => set({ product_url: e.target.value })} placeholder="https://…" />
        </Field>
        <Field label="Product version">
          <Input value={value.product_version} onChange={(e) => set({ product_version: e.target.value })} placeholder="1.0.0" />
        </Field>
      </div>

      <details className="mt-4 group">
        <summary className="text-xs font-medium text-gray-500 dark:text-slate-400 cursor-pointer select-none hover:text-gray-700 dark:hover:text-slate-200">
          Authentication &amp; optional test scope
        </summary>
        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-3.5">
          <Field label="Authorization header" hint="Sent to the deployed APIs. Never stored, never shown again after submit.">
            {authArmed ? (
              <div className="flex items-center gap-2 h-[38px]">
                <span className="font-mono text-sm text-gray-400 dark:text-slate-500 tracking-widest select-none">••••••••••••</span>
                <span className="text-[11px] text-gray-500 dark:text-slate-400">Set — hidden, sent only with execution</span>
                <button type="button" onClick={onReplaceAuth}
                  className="text-[11px] font-medium text-red-600 hover:text-red-700 underline underline-offset-2">Replace</button>
              </div>
            ) : (
              <Input type="password" autoComplete="off" value={value.authorization}
                onChange={(e) => set({ authorization: e.target.value })} placeholder="Bearer …" />
            )}
          </Field>
          <div className="flex items-end pb-2">
            <Check label="Reject unauthorized TLS" checked={value.reject_unauthorized}
              onChange={(v) => set({ reject_unauthorized: v })} />
          </div>
        </div>
        <div className="mt-3 flex flex-col gap-2">
          <span className="text-xs font-medium text-gray-600 dark:text-slate-300">Optional CTK scope</span>
          <Check label="Run optional exposed API CTKs" checked={value.run_exposed_optional} onChange={(v) => set({ run_exposed_optional: v })} />
          <Check label="Run optional security API CTKs" checked={value.run_security_optional} onChange={(v) => set({ run_security_optional: v })} />
          <Check label="Run optional dependent API CTKs" checked={value.run_dependent_optional} onChange={(v) => set({ run_dependent_optional: v })} />
        </div>
      </details>

      <div className="mt-5 flex items-center gap-3">
        <Button variant="primary" onClick={onValidate} disabled={busy || !canValidate}>
          {validating ? "Validating…" : "Validate environment"}
        </Button>
        <span className="text-xs text-gray-400 dark:text-slate-500">Validation is the required first step — it does not run the CTK.</span>
      </div>
    </Card>
  );
}
