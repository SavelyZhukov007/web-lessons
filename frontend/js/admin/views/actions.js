import { h } from '../../ui.js';
import { request } from '../../api.js';
import { pageHeader, dataTable, actionButton, confirmDialog, guarded, loading } from '../kit.js';
export async function mount(root, { signal }) {
  async function refresh() {
    const { items } = await request('/api/admin/actions?limit=200', { signal, cache: 'no-store' });
    if (signal.aborted) return;
    root.replaceChildren(pageHeader('Журнал действий'), h('p', { class: 'field-hint' }, 'Последние 200 действий. Откат не перезаписывает поздние правки и не возвращает уже отправленные уведомления.'),
      dataTable({ caption: 'Изменения данных', rows: items, empty: 'Действий пока нет', columns: [
        { label: 'Время (МСК)', cell: x => new Date(x.created_at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' }) },
        { label: 'Действие', cell: x => x.label || (x.rollback_of ? 'Отмена импорта' : 'Импорт расписания') },
        { label: 'Автор', cell: x => x.author || '—' }, { label: 'Состояние', cell: x => x.rollback_available ? 'Можно проверить откат' : 'Отменено / откат недоступен' }],
        actions: x => x.rollback_available ? [actionButton('Отменить', 'undo', async () => {
          if (await confirmDialog({ title: 'Отменить действие?', message: 'Сервер проверит последующие правки, зависимости и конфликты. Уведомления отозваны не будут.', confirmLabel: 'Отменить действие' })) {
            if (await guarded(() => request('/api/admin/actions/' + x.id + '/undo', { method: 'POST' }), 'Изменение отменено')) await refresh();
          }
        })] : [] }));
  }
  root.replaceChildren(pageHeader('Журнал действий'), loading()); await refresh();
}
