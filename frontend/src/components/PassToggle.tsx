import type { PassType } from "../api/types";

const PASSES: { value: PassType; label: string }[] = [
  { value: "ikon", label: "Ikon Pass" },
  { value: "epic", label: "Epic Pass" },
];

interface Props {
  value: PassType;
  onChange: (pass: PassType) => void;
}

export function PassToggle({ value, onChange }: Props) {
  return (
    <fieldset className="pass-toggle">
      <legend className="visually-hidden">Pass</legend>
      {PASSES.map((p) => (
        <label key={p.value} className="pass-btn">
          <input
            type="radio"
            name="pass"
            value={p.value}
            checked={value === p.value}
            onChange={() => onChange(p.value)}
          />
          <span>{p.label}</span>
        </label>
      ))}
    </fieldset>
  );
}
