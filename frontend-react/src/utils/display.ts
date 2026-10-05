export const MAX_COMPLAINT_LENGTH = 3000

export function characterCount(value: string): number {
  return Array.from(value).length
}

export function displayValue(value: string): string {
  return value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, letter => letter.toUpperCase())
}
