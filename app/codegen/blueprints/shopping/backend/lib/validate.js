// Small, dependency-free validation helpers used by every route.
export class HttpError extends Error {
  constructor(status, message, details = undefined) {
    super(message);
    this.status = status;
    this.details = details;
  }
}

export function requireString(value, field, { min = 1, max = 500, pattern } = {}) {
  if (typeof value !== 'string') throw new HttpError(422, `${field} is required.`);
  const trimmed = value.trim();
  if (trimmed.length < min) throw new HttpError(422, `${field} must be at least ${min} characters.`);
  if (trimmed.length > max) throw new HttpError(422, `${field} must be at most ${max} characters.`);
  if (pattern && !pattern.test(trimmed)) throw new HttpError(422, `${field} has an invalid format.`);
  return trimmed;
}

export function optionalString(value, field, options = {}) {
  if (value === undefined || value === null || value === '') return '';
  return requireString(value, field, options);
}

export function requireEmail(value) {
  const email = requireString(value, 'Email', { max: 254 }).toLowerCase();
  if (!/^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i.test(email)) throw new HttpError(422, 'Enter a valid email address.');
  return email;
}

export function requirePassword(value) {
  if (typeof value !== 'string' || value.length < 8) throw new HttpError(422, 'Password must be at least 8 characters.');
  if (value.length > 128) throw new HttpError(422, 'Password must be at most 128 characters.');
  if (!/[a-z]/i.test(value) || !/[0-9]/.test(value)) throw new HttpError(422, 'Password must contain letters and numbers.');
  return value;
}

export function requireInt(value, field, { min = 1, max = 99 } = {}) {
  const parsed = Number(value);
  if (!Number.isInteger(parsed)) throw new HttpError(422, `${field} must be a whole number.`);
  if (parsed < min || parsed > max) throw new HttpError(422, `${field} must be between ${min} and ${max}.`);
  return parsed;
}

export function requireEnum(value, field, allowed) {
  if (!allowed.includes(value)) throw new HttpError(422, `${field} must be one of: ${allowed.join(', ')}.`);
  return value;
}

export function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, (char) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[char]));
}

export function slugify(value) {
  return String(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 80);
}
