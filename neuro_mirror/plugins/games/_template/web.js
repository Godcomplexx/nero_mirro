/* Browser renderer contract for one game. Keep scoring on the Python side.
 * `api.start()` and `api.answer(payload)` use the common game endpoints.
 * Return an optional cleanup function from mount().
 */
export function mount({ container, definition, api, close }) {
  throw new Error(`Renderer for ${definition.code} is not implemented`);
}
