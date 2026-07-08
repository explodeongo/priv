"use client";
import { Card, Badge } from "../../components/ui";
import { Contract, ContractApi, requirementChip, CONTRACT_ONLY_CHIP } from "../../lib/odaCtk";

// Canonical contract view — REQUIREMENTS, not results. Neutral chips only; no green PASS.
function ApiRow({ api }: { api: ContractApi }) {
  const chip = requirementChip(api.requirement_status);
  return (
    <div className="flex items-start justify-between gap-3 py-2 border-b border-gray-100 dark:border-slate-800 last:border-0">
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-mono text-sm font-semibold text-gray-900 dark:text-slate-100">{api.id}</span>
          <span className="text-sm text-gray-600 dark:text-slate-300 truncate">{api.name}</span>
        </div>
        <div className="text-xs text-gray-400 dark:text-slate-500 mt-0.5">
          {api.declared_version ? <>Declared version <span className="font-mono">{api.declared_version}</span></> : "version not declared"}
          {api.api_type && api.api_type !== "openapi" && <> · apiType <span className="font-mono">{api.api_type}</span></>}
        </div>
      </div>
      <Badge tone={chip.tone}>{chip.label}</Badge>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-[11px] font-semibold uppercase tracking-wider text-gray-400 dark:text-slate-500 mb-1.5">{title}</div>
      {children}
    </div>
  );
}

export default function ODAContractPanel({ contract }: { contract: Contract }) {
  const c = contract.component;
  const req = contract.requirements;
  const core = req.exposed.filter((a) => a.segment === "CORE" && !a.is_placeholder);
  const coreMand = core.filter((a) => a.requirement_status === "MANDATORY");
  const coreOpt = core.filter((a) => a.requirement_status === "OPTIONAL");
  const security = req.exposed.filter((a) => a.segment === "SECURITY" && !a.is_placeholder);
  const management = req.exposed.filter((a) => a.segment === "MANAGEMENT" && !a.is_placeholder);
  const events = req.events;

  return (
    <Card className="p-5">
      {/* Component identity */}
      <div className="flex items-start justify-between gap-4 pb-4 border-b border-gray-100 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-bold text-gray-900 dark:text-slate-100">{c.id}</span>
            <h2 className="text-lg font-bold text-gray-900 dark:text-slate-100">{c.name}</h2>
          </div>
          <div className="flex flex-wrap gap-3 mt-1.5 text-xs text-gray-500 dark:text-slate-400">
            <span>Component version <span className="font-semibold text-gray-700 dark:text-slate-200">{c.version}</span></span>
            <span>Functional block <span className="font-semibold text-gray-700 dark:text-slate-200">{c.functionalBlock}</span></span>
            <span>Status <span className="font-semibold text-gray-700 dark:text-slate-200">{c.status}</span></span>
          </div>
        </div>
        <Badge tone="gray">{c.format}</Badge>
      </div>

      <div className="mt-4 space-y-5">
        <Group title="Core function">
          {coreMand.map((a) => <ApiRow key={a.id} api={a} />)}
          {coreOpt.map((a) => <ApiRow key={a.id} api={a} />)}
          {core.length === 0 && <p className="text-xs text-gray-400">None declared.</p>}
        </Group>

        <Group title="Security function">
          {security.length ? security.map((a) => <ApiRow key={a.id} api={a} />)
            : <p className="text-xs text-gray-400">None declared.</p>}
        </Group>

        <Group title="Management function">
          {management.length ? management.map((a) => <ApiRow key={a.id + a.name} api={a} />)
            : <p className="text-xs text-gray-400">None declared.</p>}
        </Group>

        <Group title="Dependent APIs">
          {req.real_dependent.length ? req.real_dependent.map((a) => <ApiRow key={a.id} api={a} />)
            : <p className="text-xs text-gray-500 dark:text-slate-400">None declared.</p>}
        </Group>

        <Group title="Event contract">
          <div className="flex items-center gap-4 text-sm">
            <span className="text-gray-700 dark:text-slate-200">
              <span className="font-semibold">{events.published.length}</span> published
            </span>
            <span className="text-gray-700 dark:text-slate-200">
              <span className="font-semibold">{events.subscribed.length}</span> subscribed
            </span>
            <Badge tone={CONTRACT_ONLY_CHIP.tone}>{CONTRACT_ONLY_CHIP.label}</Badge>
          </div>
          <p className="text-xs text-gray-400 dark:text-slate-500 mt-1.5">
            Contract declaration only — event conformance is not executed by this CTK framework.
          </p>
        </Group>
      </div>

      <p className="text-[11px] text-gray-400 dark:text-slate-500 mt-5 pt-3 border-t border-gray-100 dark:border-slate-800">
        Canonical contract resolved deterministically from the TM Forum ODA component specification — these are
        requirements, not test results.
      </p>
    </Card>
  );
}
