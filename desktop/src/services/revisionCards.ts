/** Revision cards saved from Lesson Mode on this device. */

export const REVISION_CARDS_KEY = "olevel.savedRevisionCards";

export type SavedRevisionCard = {
  front: string;
  back: string;
  savedAt: string;
};

export function loadSavedRevisionCards(): SavedRevisionCard[] {
  try {
    const raw = localStorage.getItem(REVISION_CARDS_KEY);
    if (!raw) return [];
    const list = JSON.parse(raw) as SavedRevisionCard[];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

export function saveRevisionCard(front: string, back: string): SavedRevisionCard[] {
  const card: SavedRevisionCard = {
    front,
    back,
    savedAt: new Date().toISOString(),
  };
  try {
    const list = loadSavedRevisionCards().filter(
      (c) => !(c.front === front && c.back === back),
    );
    list.unshift(card);
    const trimmed = list.slice(0, 50);
    localStorage.setItem(REVISION_CARDS_KEY, JSON.stringify(trimmed));
    return trimmed;
  } catch {
    return [card];
  }
}
