// Keep the editable draft independent of a submitted request and its refresh.
export function createDraftSubmit({input, button, submit, afterSuccess}) {
  let pending = false;
  let revision = 0;
  input.addEventListener('input', () => revision++);
  return async event => {
    event?.preventDefault();
    if (pending) return false;
    pending = true;
    button.disabled = true;
    const submitted = input.value;
    const submittedRevision = revision;
    try {
      const result = await submit(submitted);
      if (!result) return false;
      if (revision === submittedRevision && input.value === submitted)
        input.value = '';
      await afterSuccess?.(result);
      return true;
    } finally {
      pending = false;
      button.disabled = false;
    }
  };
}
