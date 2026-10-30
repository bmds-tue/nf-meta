// The session token printed by `nf-meta editor`: it arrives in the page's link
// (`?token=…`) and goes with every API request

export const TOKEN_HEADER = 'X-NF-Meta-Token'
const STORAGE_KEY = 'nf-meta-token'

let token: string | null = null

// The token in a URL and the URL without it
export function splitToken(href: string): { token: string | null, url: string } {
  const url = new URL(href)
  const found = url.searchParams.get('token')
  url.searchParams.delete('token')
  return { token: found, url: url.toString() }
}

// Take the token from the page's address (and remove it there), or the one kept for this tab
export function initAccessToken() {
  const { token: fromUrl, url } = splitToken(window.location.href)
  if (fromUrl) {
    token = fromUrl
    window.history.replaceState(window.history.state, '', url)
    try { sessionStorage.setItem(STORAGE_KEY, fromUrl) } catch { /* kept in memory only */ }
    return
  }
  try { token = sessionStorage.getItem(STORAGE_KEY) } catch { token = null }
}

export function accessHeaders(): Record<string, string> {
  return token ? { [TOKEN_HEADER]: token } : {}
}
