export const SOURCE_PAGE_SIZE = 200;

export function pageForLine(line: number) {
  return Math.floor(Math.max(0, line - 1) / SOURCE_PAGE_SIZE);
}

export function isSelectedLine(line: number, start: number, end: number) {
  return line >= start && line <= end;
}
