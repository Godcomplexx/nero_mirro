/* Browser renderer contract for the Math Quiz game. Keep scoring on the Python side. */
export function mount({ container, definition, api, close }) {
    let sessionId = null;
    let totalQuestions = 0;

    // Создаем базовую разметку
    const wrapper = document.createElement('div');
    wrapper.style.cssText = 'font-family: sans-serif; padding: 20px; max-width: 400px; margin: auto; text-align: center; border: 1px solid #ccc; border-radius: 8px;';
    
    const title = document.createElement('h2');
    title.textContent = 'Математический квиз';
    
    const progressEl = document.createElement('p');
    progressEl.style.color = '#666';
    progressEl.style.fontSize = '0.9em';

    const questionEl = document.createElement('p');
    questionEl.style.fontSize = '1.2em';
    questionEl.style.fontWeight = 'bold';
    questionEl.style.minHeight = '1.5em';
    
    const feedbackEl = document.createElement('p');
    feedbackEl.style.minHeight = '1.5em';
    feedbackEl.style.fontWeight = 'bold';
    
    const input = document.createElement('input');
    input.type = 'number';
    input.style.cssText = 'padding: 8px; font-size: 1em; width: 100px; text-align: center;';
    
    const submitBtn = document.createElement('button');
    submitBtn.textContent = 'Ответить';
    submitBtn.style.cssText = 'padding: 8px 16px; font-size: 1em; margin-left: 10px; cursor: pointer;';
    
    const inputRow = document.createElement('div');
    inputRow.style.marginTop = '20px';
    inputRow.appendChild(input);
    inputRow.appendChild(submitBtn);

    wrapper.append(title, progressEl, questionEl, feedbackEl, inputRow);
    container.appendChild(wrapper);

    // Функция обновления UI на основе ответа от бэкенда
    function updateUI(data) {
        if (data.status === 'completed') {
            questionEl.textContent = 'Результат:';
            feedbackEl.textContent = `Правильных ответов: ${data.score} из ${data.total_questions}`;
            feedbackEl.style.color = data.score === data.total_questions ? 'green' : 'orange';
            inputRow.style.display = 'none';
            progressEl.textContent = `Время прохождения: ${data.duration_seconds} сек.`;
            
            const closeBtn = document.createElement('button');
            closeBtn.textContent = 'Закрыть игру';
            closeBtn.style.marginTop = '20px';
            closeBtn.style.padding = '10px 20px';
            closeBtn.onclick = () => close();
            wrapper.appendChild(closeBtn);
            return;
        }

        questionEl.textContent = data.current_question;
        progressEl.textContent = `Вопрос ${data.question_number} из ${totalQuestions}`;
        input.value = '';
        input.focus();
        
        if (data.feedback) {
            feedbackEl.textContent = data.feedback;
            feedbackEl.style.color = data.feedback.includes('Верно') ? 'green' : 'red';
        } else {
            feedbackEl.textContent = '';
        }
    }

    // Отправка ответа
    async function submitAnswer() {
        if (!input.value && input.value !== '0') return;
        submitBtn.disabled = true;
        
        const res = await api.answer({
            session_id: sessionId,
            answer: input.value
        });
        
        submitBtn.disabled = false;
        updateUI(res);
    }

    // Запуск игры
    async function startGame() {
        const res = await api.start({});
        if (res.status === 'started') {
            sessionId = res.session_id;
            totalQuestions = res.total_questions;
            updateUI(res);
        }
    }

    submitBtn.addEventListener('click', submitAnswer);
    input.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') submitAnswer();
    });

    startGame();

    // Optional cleanup function
    return () => {
        container.innerHTML = '';
    };
}
