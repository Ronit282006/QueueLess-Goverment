/** Canonical citizen profile categories used for account registration and admin priority rules.
 *
 * The `code` is the stable, lowercase tag stored on the user / priority rule. The
 * human-readable label is provided via i18n keys `tag.<code>`. Keeping the codes
 * canonical means a citizen who selects “Person with disability” at signup is
 * matched by an admin rule tagged `disability`.
 */
export interface CitizenTag {
  code: string
}

export const CITIZEN_TAGS: CitizenTag[] = [
  { code: 'senior' },
  { code: 'disability' },
  { code: 'pregnant' },
  { code: 'chronic' },
  { code: 'veteran' },
  { code: 'bpl' },
  { code: 'widow' },
  { code: 'single_parent' },
  { code: 'transgender' },
]

export const CITIZEN_TAG_CODES = CITIZEN_TAGS.map((c) => c.code)