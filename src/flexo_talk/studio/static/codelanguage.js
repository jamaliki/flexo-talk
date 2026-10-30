// The language a listing's words are coloured as (flexo_talk.codecolours), chosen in its
// inspector: Automatic -- the one they look like -- or one of those the deck's catalogue
// offers, Plain Text last (coloured by nothing). A language written into the deck that is
// not offered is shown as it is written.

export function languageField({ ui, catalog, value, key, onChange }) {
  const offered = catalog?.languages || [];
  const plain = offered.filter((each) => each.value === "text");
  const named = offered.filter((each) => each.value !== "text");
  const own = value && !offered.some((each) => each.value === value) ? [{ value, label: value }] : [];
  return ui.field("Language", ui.select({ value: value || "", key, onChange,
    options: [{ value: "", label: "Automatic" }, { line: true }, ...own, ...named, ...(plain.length ? [{ line: true }, ...plain] : [])] }));
}
