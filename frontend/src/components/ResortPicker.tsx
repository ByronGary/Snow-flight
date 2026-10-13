import { useCombobox } from "downshift";
import { useEffect, useMemo, useState } from "react";
import type { PassType, Resort } from "../api/types";
import { fold } from "../lib/text";

const COUNTRY_NAMES: Record<string, string> = {
  US: "USA", CA: "Canada", FR: "France", NZ: "New Zealand", AU: "Australia", CL: "Chile",
  JP: "Japan", SE: "Sweden", CH: "Switzerland", AR: "Argentina", AD: "Andorra", NO: "Norway",
  IT: "Italy", AT: "Austria",
};

export function resortLocation(r: Resort): string {
  return `${r.region}, ${COUNTRY_NAMES[r.country] ?? r.country}`;
}

interface Props {
  resorts: Resort[];
  pass: PassType;
  selected: Resort | null;
  onSelect: (resort: Resort | null) => void;
}

/**
 * Searchable resort list. Only the current pass's resorts are rendered, which
 * also avoids iOS Safari ignoring `hidden` on <option> elements.
 */
export function ResortPicker({ resorts, pass, selected, onSelect }: Props) {
  const options = useMemo(
    () => resorts.filter((r) => r.pass === pass).sort((a, b) => a.name.localeCompare(b.name)),
    [resorts, pass],
  );
  const [inputValue, setInputValue] = useState(selected?.name ?? "");

  useEffect(() => {
    setInputValue(selected?.name ?? "");
  }, [selected]);

  const items = useMemo(() => {
    const q = fold(inputValue.trim());
    if (!q || (selected && inputValue === selected.name)) return options;
    return options.filter((r) => fold(`${r.name} ${resortLocation(r)}`).includes(q));
  }, [options, inputValue, selected]);

  const { isOpen, highlightedIndex, getLabelProps, getInputProps, getMenuProps, getItemProps, getToggleButtonProps } =
    useCombobox<Resort>({
      items,
      inputValue,
      selectedItem: selected,
      itemToString: (r) => r?.name ?? "",
      itemToKey: (r) => r?.slug,
      onInputValueChange: ({ inputValue: value }) => setInputValue(value ?? ""),
      onSelectedItemChange: ({ selectedItem }) => onSelect(selectedItem ?? null),
    });

  const passLabel = pass === "ikon" ? "Ikon" : "Epic";

  return (
    <div className="combobox">
      <label {...getLabelProps()} className="field-label">
        Resort
      </label>
      <div className="combobox-control">
        <input
          {...getInputProps({ placeholder: `Search ${options.length} ${passLabel} resorts…` })}
          className="text-input"
        />
        <button type="button" className="combobox-toggle" aria-label="Show resorts" {...getToggleButtonProps()}>
          <svg width="12" height="8" viewBox="0 0 12 8" aria-hidden="true">
            <path d="M1 1l5 5 5-5" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" />
          </svg>
        </button>
      </div>
      <ul {...getMenuProps()} className={`combobox-menu${isOpen ? " open" : ""}`}>
        {isOpen &&
          items.map((r, index) => (
            <li
              key={r.slug}
              className={`combobox-item${highlightedIndex === index ? " highlighted" : ""}${
                selected?.slug === r.slug ? " selected" : ""
              }`}
              {...getItemProps({ item: r, index })}
            >
              <span>{r.name}</span>
              <span className="muted">{resortLocation(r)}</span>
            </li>
          ))}
        {isOpen && items.length === 0 && <li className="combobox-empty">No {passLabel} resorts match “{inputValue}”</li>}
      </ul>
    </div>
  );
}
