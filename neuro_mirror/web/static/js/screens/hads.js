// neuro_mirror/web/static/js/screens/hads.js
//
// «Проверка самочувствия»: the HADS test (14 statements, 4 options each) in
// the work area. Questions and scoring come from the server; the score is
// never shown to the patient — only a neutral "saved" confirmation (spec §6).

import { hadsController } from "../core/hads-controller.js";
import { createHadsView } from "../components/hads-test.js";
import { createTestScreen } from "./test-screen.js";

export const hadsScreen = createTestScreen({
  scenario: "hads",
  subtitle: "Тест на тревожность и депрессию — цифровая версия шкалы HADS",
  introTitle: "Перед началом",
  introText:
    "Тест состоит из 14 утверждений. Для каждого выберите вариант, который лучше всего описывает ваше состояние за последнюю неделю. Сначала проверим микрофон — это займёт несколько секунд.",
  startUrl: "/api/actions/start_hads",
  controller: hadsController,
  createView: createHadsView,
  doneTitle: "Спасибо! Тест завершён",
  doneText: "Ваши ответы сохранены в профиле. Результат доступен специалисту в разделе «Отчёты».",
  stoppedTitle: "Тест прерван",
  leaveWarning: {
    title: "Тест ещё не завершён",
    message: "Если перейти в другой раздел, тест продолжится. Вернуться к нему можно через «Проверка самочувствия» в меню.",
  },
});
