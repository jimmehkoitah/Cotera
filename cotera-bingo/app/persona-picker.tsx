'use client';

export type PersonaOption = {
  id: string;
  label: string;
  description: string;
};

type Props = {
  options: readonly PersonaOption[];
  disabled?: boolean;
  selectedId?: string | null;
  onSelect: (persona: PersonaOption) => void;
};

/** Role families derived from the supplied persona reference. */
export default function PersonaPicker({options, selectedId, onSelect, disabled}: Props) {
  return (
    <section className="persona-picker" aria-labelledby="persona-title">
      <span className="eyebrow">START WITH YOUR WORLD</span>
      <h1 id="persona-title">What kind of work do you do?</h1>
      <p>Choose the team or workflow you want to talk about.</p>
      <div className="persona-options" role="group" aria-label="Your role">
        {options.map((persona) => (
          <button
            type="button"
            disabled={disabled}
            className="persona-option"
            key={persona.id}
            aria-pressed={selectedId === persona.id}
            onClick={() => onSelect(persona)}
          >
            <span>{persona.label}</span>
            <small>{persona.description}</small>
          </button>
        ))}
      </div>
    </section>
  );
}
