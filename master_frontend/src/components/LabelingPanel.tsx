"use client";

interface Props {
  activeLabel: number;
  onLabel: (id: number) => void;
  disabled: boolean;
}

// Labels 1-50 per MIGRATION_PLAN.md open decision #3.
const LABELS = Array.from({ length: 50 }, (_, i) => i + 1);

export default function LabelingPanel({ activeLabel, onLabel, disabled }: Props) {
  return (
    <div>
      <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-2">
        Labels {activeLabel > 0 && <span className="text-blue-400 normal-case">— active: {activeLabel}</span>}
      </h3>
      <div className="grid grid-cols-10 gap-1 max-h-36 overflow-y-auto pr-1">
        {LABELS.map(id => (
          <button
            key={id}
            onClick={() => onLabel(id)}
            disabled={disabled}
            className={`
              rounded py-1 text-xs font-mono font-bold transition-colors
              ${activeLabel === id
                ? "bg-blue-600 text-white"
                : "bg-[#161b22] text-gray-400 hover:bg-[#1c2230] hover:text-white"}
              disabled:opacity-30 disabled:cursor-not-allowed
            `}
          >
            {id}
          </button>
        ))}
      </div>
    </div>
  );
}
