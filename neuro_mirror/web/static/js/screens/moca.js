// neuro_mirror/web/static/js/screens/moca.js
//
// «Когнитивный тест»: the voice MoCA test (11 tasks) in the work area. Task
// texts, voiced instructions, recording and scoring come from the server.
// The result card stays neutral: whether the patient sees domain bars or a
// total score is still to be decided with the psychologist (deck slide 8).

import { mocaController } from "../core/moca-controller.js";
import { createMocaView } from "../components/moca-test.js";
import { createTestScreen } from "./test-screen.js";

export const mocaScreen = createTestScreen({
  scenario: "moca",
  subtitle: "Аудио-MoCA — 11 заданий с голосовыми инструкциями",
  introTitle: "Перед началом",
  introText:
    "Инструкции к заданиям звучат голосом и показываются на экране. Отвечайте вслух. Сначала проверим микрофон и сделаем пробу голоса — это займёт несколько секунд.",
  startUrl: "/api/actions/start_moca",
  controller: mocaController,
  createView: createMocaView,
  doneTitle: "Тест завершён",
  doneText: "Все задания выполнены, результаты сохранены. Их можно посмотреть в разделе «Отчёты».",
  stoppedTitle: "Тест прерван",
  leaveWarning: {
    title: "Тест ещё не завершён",
    message: "Если перейти в другой раздел, тест продолжится. Вернуться к нему можно через «Когнитивный тест» в меню.",
  },
});
