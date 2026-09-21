# Naver Place transport investigation — 2026-09-21

## Outcome

The Python integration retrieved Place 18199503 directly with `aiohttp` and a
`DummyCookieJar`. No login, browser process, CAPTCHA token, proxy, or additional
runtime dependency was used. This is a point-in-time verification, not a promise
that Naver's unofficial web endpoints will remain available.

The response contained:

- Name: 라온동물병원; representative image URL present.
- September 21 opening: 10:00–19:00; break: 12:30–13:30.
- September 24–26: 추석 연휴, fully closed.
- September 27: 정기휴무.

## Controlled transport comparison

| Request | Observed result |
| --- | --- |
| Previous truncated User-Agent, with `from=map&locale=ko` | 7,093-character restriction document; no Apollo data |
| Complete document header profile, original `/pet/18199503/home` URL | 590,573-character document; Apollo data present |
| Complete document header profile, `from=map&locale=ko` | 590,990-character document; Apollo data present |
| Updated integration with aiohttp and cookie storage disabled | Summary, photo, normalized hours and closures returned |

Adding query parameters alone did not solve the problem; changing the document
request header profile did. The comparison isolates the header profile, not
each individual header. Therefore the exact internal Naver rule is unknown.
The code now sends a fixed, complete compatibility User-Agent, HTML Accept,
Korean Accept-Language and the map Referer. JSON endpoints use JSON Accept.
There is no rotating client identity or token replay.

## Available paths and their limitations

1. Public instant search needs `coords=latitude,longitude`. Omitting it produced
   HTTP 500 in the prior investigation. Search is capped at ten candidates, so
   the flow requires explicit name/address selection instead of assuming a
   unique match across all Naver places.
2. Public place summary provides the identity, category, coordinates, address
   and representative pictures. It does not provide a complete daily schedule.
3. Public Place HTML embeds `window.__APOLLO_STATE__`. The parser reads JSON,
   verifies the selected place reference, and extracts `newBusinessHours`,
   `breakHours` and `comingIrregularClosedDays`. It does not execute page code.
4. The [official Local Search API](https://developers.naver.com/docs/serviceapi/search/local/local.md)
   documents name/address/link/coordinates, not opening hours or holiday ranges.
   It therefore does not replace the schedule source.
5. The [official CAPTCHA API](https://developers.naver.com/docs/utils/captcha/overview/)
   issues challenges for applications and validates human input. It is not a
   documented authorization API for Naver Map. The supplied `ncpt` encrypted
   payload is not used or persisted; no CAPTCHA work is needed by the verified
   public HTML path.

## Error handling and regression coverage

- Distinguish HTTP 401/403, 429, other non-200 responses, HTTP-200 restriction
  pages, changed page structure, and malformed/mismatched place data.
- Preserve basic place information when the hours document fails; expose
  `hours_error` and `hours_error_code`. Do not report stale hours as current.
- Never follow redirects to another origin or retry a rejected request within
  the call. A later normal refresh can recover without retained error state.
- Enforce a 5 MB document limit, request timeout, fixed numeric place IDs,
  CDN image allow-list and bounded data extraction.
- Tests assert the actual request headers and cover restricted → recovered
  responses, holiday precedence, breaks, calendar-day boundaries and explicit
  24-hour operation (00:00–00:00 is accepted only with `showEndsNextDay=true`).

Real Home Assistant UI deployment and other users' network paths were not
tested. Genuine future access restrictions remain errors, not grounds to
rotate IPs/accounts or bypass interactive verification.
