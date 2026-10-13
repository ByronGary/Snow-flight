/** Lowercase and strip accents so "isere" matches "Val d'Isère". */
export function fold(s: string): string {
  return s.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase();
}
