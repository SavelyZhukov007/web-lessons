// Один актуальный запрос на сценарий. Отмена работает и до debounce, и для транспорта без AbortSignal.
export function latestRequest() {
  let generation = 0, active;
  function cancel() { generation++; active?.abort(); }
  return {
    cancel,
    begin() {
      cancel();
      const mine = generation, controller = active = new AbortController();
      return { signal: controller.signal, isCurrent: () => mine === generation && !controller.signal.aborted };
    },
  };
}
