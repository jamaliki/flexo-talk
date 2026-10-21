// The people beside a slide's title (`people`, in the deck's document): a list, each a
// picture file -- or `{ image, name }` with their name set small under their portrait.
// What the editor does to them, worked out from the slide alone, with no page, so it can be
// tried without one. Written back as written: a person with no name as their file alone.

// The layouts whose title may have people beside it (deck.py's PEOPLE_LAYOUTS).
export const PEOPLE_LAYOUTS = new Set(["content", "two-columns", "columns", "figure"]);

export const canHavePeople = (slide) => PEOPLE_LAYOUTS.has(slide?.layout || "content");

// Its people as `{ image, name }` each, in their order ("" where they have no name).
export function peopleOf(slide) {
  const value = slide?.people;
  if (!Array.isArray(value)) return [];
  return value.map((item) => (item && typeof item === "object"
    ? { image: String(item.image ?? ""), name: item.name == null ? "" : String(item.name) }
    : { image: String(item ?? ""), name: "" }));
}

// The list written back: a person with no name as their file alone; none left, no key (nor
// a size or a place for them).
export function setPeople(slide, people) {
  const written = people.map(({ image, name }) => (String(name ?? "").trim() ? { image, name } : image));
  if (written.length) slide.people = written; else { delete slide.people; delete slide.people_size; delete slide.people_at; }
}

// How wide each of its portraits is (`people_size`, in points); null, as wide as the title
// sets them.
export const peopleSize = (slide) => (typeof slide?.people_size === "number" ? slide.people_size : null);

// Every portrait `size` points across, kept between `least` and `most` and to a whole point;
// null, as the title sets them. Whether that changed it.
export function setPeopleSize(slide, size, [least, most] = [24, 160]) {
  const value = size === null || size === undefined ? null : Math.round(Math.min(most, Math.max(least, size)));
  if (value === peopleSize(slide)) return false;
  if (value === null) delete slide.people_size; else slide.people_size = value;
  return true;
}

// People added at `at` (else at the end), each a picture file.
export function addPeople(slide, images, at = null) {
  const people = peopleOf(slide);
  const where = at === null || at === undefined ? people.length : Math.max(0, Math.min(at, people.length));
  people.splice(where, 0, ...images.map((image) => ({ image, name: "" })));
  setPeople(slide, people);
  return where;
}

export function removePerson(slide, index) {
  const people = peopleOf(slide);
  if (index < 0 || index >= people.length) return;
  people.splice(index, 1);
  setPeople(slide, people);
}

export function movePerson(slide, from, to) {
  const people = peopleOf(slide);
  if (from < 0 || from >= people.length || to < 0 || to >= people.length || from === to) return;
  const [moved] = people.splice(from, 1);
  people.splice(to, 0, moved);
  setPeople(slide, people);
}

export function renamePerson(slide, index, name) {
  const people = peopleOf(slide);
  if (index < 0 || index >= people.length) return;
  people[index] = { ...people[index], name };
  setPeople(slide, people);
}

export function replacePortrait(slide, index, image) {
  const people = peopleOf(slide);
  if (index < 0 || index >= people.length) return;
  people[index] = { ...people[index], image };
  setPeople(slide, people);
}

// Where they stand placed freely (`people_at`: the row's top left, [x, y] in the units the
// slide's shapes are placed in, as an object's `at` is); null, beside the title.
export function peopleAt(slide) {
  const value = slide?.people_at;
  return Array.isArray(value) && value.length === 2 && value.every((item) => Number.isFinite(Number(item))) ? value.map(Number) : null;
}

// Placed at `at` (to a hundredth, as an object's place is written); null, back beside the
// title. Whether that changed it.
export function setPeopleAt(slide, at) {
  const value = at ? at.map((item) => Math.round(Number(item) * 100) / 100) : null;
  const was = peopleAt(slide);
  if (value === null ? was === null : was !== null && was[0] === value[0] && was[1] === value[1]) return false;
  if (value === null) delete slide.people_at; else slide.people_at = value;
  return true;
}
