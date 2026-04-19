"use client";

interface Props {
  subject: string; setSubject: (v: string) => void;
  sessionTag: string; setSessionTag: (v: string) => void;
  operator: string; setOperator: (v: string) => void;
  disabled: boolean;
}

export default function SessionForm({ subject, setSubject, sessionTag, setSessionTag, operator, setOperator, disabled }: Props) {
  return (
    <div className="space-y-2">
      <h3 className="text-xs font-bold text-gray-400 uppercase tracking-wider">Session Info</h3>
      {[
        { label: "Subject", value: subject, set: setSubject, placeholder: "Subject_001" },
        { label: "Tag", value: sessionTag, set: setSessionTag, placeholder: "Sesi_Pagi" },
        { label: "Operator", value: operator, set: setOperator, placeholder: "Farhan" },
      ].map(({ label, value, set, placeholder }) => (
        <div key={label}>
          <label className="text-xs text-gray-500">{label}</label>
          <input
            className="w-full mt-0.5 px-2 py-1.5 rounded bg-[#161b22] border border-[#30363d] text-sm text-white
                       focus:outline-none focus:border-blue-500 disabled:opacity-40"
            value={value}
            onChange={e => set(e.target.value)}
            placeholder={placeholder}
            disabled={disabled}
          />
        </div>
      ))}
    </div>
  );
}
