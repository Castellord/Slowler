import React, { useState, useRef, useEffect } from 'react';
import io from 'socket.io-client';

function App() {
  const [files, setFiles] = useState([]);
  const [globalSpeed, setGlobalSpeed] = useState(0.5);
  const [preservePitch, setPreservePitch] = useState(true);
  const [outputFormat, setOutputFormat] = useState('wav'); // 'wav' или 'mp3'
  const [saveLog, setSaveLog] = useState(false); // Сохранение лога в файл
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('');
  const [backendStatus, setBackendStatus] = useState('checking');
  const [processingLog, setProcessingLog] = useState([]);
  const [currentFile, setCurrentFile] = useState('');
  const [socket, setSocket] = useState(null);
  const [socketConnected, setSocketConnected] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef(null);

  // Проверяем статус бекенда при загрузке и инициализируем WebSocket
  useEffect(() => {
    checkBackendHealth();
    initializeWebSocket();
    
    return () => {
      if (socket) {
        socket.disconnect();
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const initializeWebSocket = () => {
    try {
      // Определяем URL для WebSocket в зависимости от окружения
      const socketUrl = process.env.NODE_ENV === 'production' 
        ? window.location.origin  // В production используем текущий домен
        : 'http://localhost:5230'; // В development используем localhost
      
      console.log('🔌 Инициализация WebSocket:', socketUrl);
      
      const newSocket = io(socketUrl, {
        transports: ['polling', 'websocket'], // Сначала пробуем polling, потом websocket
        timeout: 10000,
        reconnection: true,
        reconnectionDelay: 2000,
        reconnectionAttempts: 3
      });

      newSocket.on('connect', () => {
        console.log('🔌 WebSocket подключен');
        setSocketConnected(true);
        addToLog('📡 WebSocket подключение установлено', 'success');
      });

      newSocket.on('disconnect', () => {
        console.log('🔌 WebSocket отключен');
        setSocketConnected(false);
        addToLog('📡 WebSocket подключение потеряно', 'error');
      });

      newSocket.on('progress_update', (data) => {
        console.log('📡 Получен прогресс через WebSocket:', data);
        
        // Добавляем сообщение от backend в лог
        addBackendLogEntry(data);
        
        // Обновляем прогресс на основе данных от сервера
        if (data.file_index !== undefined && data.total_files !== undefined) {
          updateProgress(data.file_index, data.total_files, data.step || 0, data.message);
        }
        
        if (data.type === 'complete') {
          addToLog('🎉 Обработка полностью завершена!', 'success');
        }
      });

      newSocket.on('connect_error', (error) => {
        console.error('❌ Ошибка WebSocket подключения:', error);
        setSocketConnected(false);
      });

      setSocket(newSocket);
    } catch (error) {
      console.error('❌ Ошибка инициализации WebSocket:', error);
      setSocketConnected(false);
    }
  };

  const checkBackendHealth = async () => {
    try {
      const response = await fetch('/health');
      if (response.ok) {
        setBackendStatus('connected');
        setMessage('✅ Подключение к серверу обработки установлено');
        setMessageType('success');
        setTimeout(() => setMessage(''), 3000);
      } else {
        setBackendStatus('error');
      }
    } catch (error) {
      setBackendStatus('error');
      setMessage('❌ Сервер обработки недоступен. Запустите Python бекенд.');
      setMessageType('error');
    }
  };

  const processSelectedFiles = (selectedFiles) => {
    const audioFiles = selectedFiles.filter(file => 
      file.type === 'audio/mp3' || file.type === 'audio/wav' || 
      file.type === 'audio/mpeg' || file.type === 'audio/x-wav'
    );

    if (audioFiles.length !== selectedFiles.length) {
      setMessage('Некоторые файлы были пропущены. Поддерживаются только MP3 и WAV файлы.');
      setMessageType('error');
      setTimeout(() => setMessage(''), 3000);
    }

    if (audioFiles.length > 0) {
      const newFiles = audioFiles.map((file, index) => ({
        id: Date.now() + index,
        file: file,
        name: file.name,
        size: file.size,
        speed: globalSpeed
      }));

      setFiles(prev => [...prev, ...newFiles]);
      
      // Показываем сообщение об успешном добавлении
      setMessage(`✅ Добавлено ${audioFiles.length} файл(ов)`);
      setMessageType('success');
      setTimeout(() => setMessage(''), 2000);
    }
  };

  const handleFileSelect = (event) => {
    const selectedFiles = Array.from(event.target.files);
    processSelectedFiles(selectedFiles);
    event.target.value = '';
  };

  // Обработчики drag-and-drop
  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (backendStatus === 'connected') {
      setDragActive(true);
    }
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    // Проверяем, что курсор действительно покинул область загрузки
    // а не просто перешел на дочерний элемент
    const rect = e.currentTarget.getBoundingClientRect();
    const x = e.clientX;
    const y = e.clientY;
    
    if (x < rect.left || x >= rect.right || y < rect.top || y >= rect.bottom) {
      setDragActive(false);
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
    
    // Убеждаемся, что состояние активно при движении курсора
    if (backendStatus === 'connected' && !dragActive) {
      setDragActive(true);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (backendStatus !== 'connected') {
      return;
    }

    const droppedFiles = Array.from(e.dataTransfer.files);
    if (droppedFiles.length > 0) {
      processSelectedFiles(droppedFiles);
    }
  };

  const removeFile = (id) => {
    setFiles(files.filter(file => file.id !== id));
  };

  const updateFileSpeed = (id, speed) => {
    setFiles(files.map(file => 
      file.id === id ? { ...file, speed: parseFloat(speed) } : file
    ));
  };

  const applyGlobalSpeed = () => {
    setFiles(files.map(file => ({ ...file, speed: globalSpeed })));
    setMessage('Глобальная скорость применена ко всем файлам');
    setMessageType('success');
    setTimeout(() => setMessage(''), 2000);
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const addToLog = (message, type = 'info') => {
    const timestamp = new Date().toLocaleTimeString();
    setProcessingLog(prev => [...prev, { 
      id: Date.now(), 
      message, 
      type, 
      timestamp 
    }]);
  };

  const clearLog = () => {
    setProcessingLog([]);
    setCurrentFile('');
  };

  const updateProgress = (fileIndex, totalFiles, step, message) => {
    const baseProgress = (fileIndex / totalFiles) * 80; // 80% для обработки файлов
    const stepProgress = step * (80 / totalFiles); // прогресс текущего шага
    const totalProgress = Math.min(baseProgress + stepProgress, 90);
    
    setProgress(totalProgress);
    setCurrentFile(`Файл ${fileIndex + 1}/${totalFiles}: ${message}`);
    // Убираем addToLog отсюда - сообщения будут добавляться напрямую от backend
  };

  const addBackendLogEntry = (entry) => {
    const timestamp = new Date().toLocaleTimeString();
    setProcessingLog(prev => [...prev, { 
      id: Date.now() + Math.random(), // Уникальный ID
      message: entry.message, 
      type: entry.type, 
      timestamp 
    }]);
  };

  const getProcessButtonText = () => {
    if (processing) {
      return 'Обработка на сервере...';
    }

    if (files.length === 0) {
      return 'Выберите файлы для обработки';
    }

    // Подсчитываем файлы с измененной скоростью (не равной 1.0)
    const changedSpeedFiles = files.filter(file => Math.abs(file.speed - 1.0) > 0.001);
    const formatText = outputFormat.toUpperCase();

    if (changedSpeedFiles.length === 0) {
      // Все файлы имеют скорость 1.0 - только конвертация
      return `Конвертировать в ${formatText}`;
    } else {
      // Есть файлы с измененной скоростью
      return `Замедлить (${changedSpeedFiles.length}) и конвертировать в ${formatText}`;
    }
  };

  const processFiles = async () => {
    if (files.length === 0) {
      setMessage('Пожалуйста, выберите файлы для обработки');
      setMessageType('error');
      setTimeout(() => setMessage(''), 3000);
      return;
    }

    if (backendStatus !== 'connected') {
      setMessage('❌ Сервер обработки недоступен. Проверьте подключение.');
      setMessageType('error');
      setTimeout(() => setMessage(''), 3000);
      return;
    }

    setProcessing(true);
    setProgress(0);
    clearLog();
    setMessage('Подготовка к обработке...');

    try {
      // Инициализация лога (только frontend сообщения)
      addToLog('🎵 Подготовка к обработке', 'info');
      addToLog(`📁 Количество файлов: ${files.length}`, 'info');
      addToLog(`⚙️ Формат вывода: ${outputFormat.toUpperCase()}`, 'info');
      addToLog(`🎛️ Сохранение тональности: ${preservePitch ? 'Да' : 'Нет'}`, 'info');

      // Создаем FormData для отправки файлов
      const formData = new FormData();
      
      // Добавляем файлы (без логирования, это будет в backend)
      files.forEach((fileData, index) => {
        formData.append('files', fileData.file);
        formData.append('speeds', fileData.speed.toString());
      });
      
      // Добавляем настройки
      formData.append('preserve_pitch', preservePitch.toString());
      formData.append('output_format', outputFormat);
      
      // Генерируем уникальный ID сессии
      const sessionId = `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      formData.append('session_id', sessionId);

      setCurrentFile('Подключение к серверу...');
      setProgress(5);
      addToLog('📤 Подключаемся к серверу', 'info');

      setMessage('🔄 Обработка файлов на сервере...');

      // Подключаемся к WebSocket сессии для получения прогресса
      if (socket && socketConnected) {
        socket.emit('join_session', { session_id: sessionId });
        addToLog('📡 Подключились к WebSocket сессии', 'info');
      } else {
        addToLog('⚠️ WebSocket недоступен, используем fallback polling', 'warning');
      }

      // Запускаем fallback polling на случай проблем с WebSocket
      let lastProgressCount = 0;
      const pollProgress = async () => {
        try {
          const progressResponse = await fetch(`/progress/${sessionId}`);
          if (progressResponse.ok) {
            const progressData = await progressResponse.json();
            
            if (progressData.success && progressData.progress.length > lastProgressCount) {
              // Обрабатываем новые записи прогресса
              const newEntries = progressData.progress.slice(lastProgressCount);
              
              for (const entry of newEntries) {
                console.log('📊 Получен прогресс через polling:', entry);
                
                // Добавляем сообщение от backend в лог
                addBackendLogEntry(entry);
                
                // Обновляем прогресс на основе данных от сервера
                if (entry.file_index !== undefined && entry.total_files !== undefined) {
                  updateProgress(entry.file_index, entry.total_files, entry.step || 0, entry.message);
                }
                
                if (entry.type === 'complete') {
                  addToLog('🎉 Обработка полностью завершена!', 'success');
                  clearInterval(progressInterval);
                  return;
                }
              }
              
              lastProgressCount = progressData.progress.length;
            }
          }
        } catch (error) {
          console.error('Ошибка polling прогресса:', error);
        }
      };

      // Запускаем polling каждые 2 секунды как fallback
      const progressInterval = setInterval(pollProgress, 2000);

      addToLog('📤 Отправляем запрос на обработку', 'info');

      // Отправляем запрос на сервер
      const response = await fetch('/process', {
        method: 'POST',
        body: formData,
      });
      
      // Останавливаем polling после получения ответа
      clearInterval(progressInterval);

      if (!response.ok) {
        if (response.status === 413) {
          throw new Error('Файлы слишком большие. Попробуйте загрузить файлы меньшего размера или по одному.');
        }
        const errorData = await response.json().catch(() => ({ error: 'Ошибка сервера' }));
        throw new Error(errorData.error || `Ошибка сервера (${response.status})`);
      }

      setCurrentFile('Обработка завершена, получение результатов...');
      setProgress(90);
      addToLog('✅ Обработка на сервере завершена', 'success');
      addToLog('📦 Получаем обработанные файлы', 'info');

      // Получаем ZIP файл
      const blob = await response.blob();
      
      // Создаем ссылку для скачивания
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.style.display = 'none';
      a.href = url;
      a.download = 'slowed_audio_files.zip';
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      setProgress(100);
      setCurrentFile('Готово! Архив загружен.');
      setMessage('✅ Обработка завершена! Архив загружен.');
      setMessageType('success');
      addToLog('🎉 Архив успешно загружен!', 'success');

      // Автоматически скачиваем лог если включена настройка
      if (saveLog) {
        setTimeout(() => {
          downloadLog();
        }, 1000); // Небольшая задержка для завершения всех операций
      }

    } catch (error) {
      console.error('Ошибка обработки:', error);
      setMessage(`❌ Ошибка обработки: ${error.message}`);
      setMessageType('error');
      addToLog(`❌ Ошибка: ${error.message}`, 'error');
      setCurrentFile('Ошибка обработки');
    } finally {
      setProcessing(false);
      setTimeout(() => {
        setMessage('');
        setProgress(0);
        setCurrentFile('');
      }, 5230);
    }
  };

  const downloadLog = () => {
    if (processingLog.length === 0) {
      setMessage('Лог пуст, нечего скачивать');
      setMessageType('error');
      setTimeout(() => setMessage(''), 3000);
      return;
    }

    // Создаем содержимое лога
    const logContent = processingLog.map(entry => 
      `[${entry.timestamp}] ${entry.message}`
    ).join('\n');

    // Добавляем заголовок с информацией о сессии
    const timestamp = new Date().toLocaleString();
    const header = `SETINA Slowdown App - Лог обработки
Дата и время: ${timestamp}
Количество файлов: ${files.length}
Формат вывода: ${outputFormat.toUpperCase()}
Сохранение тональности: ${preservePitch ? 'Да' : 'Нет'}
WebSocket подключение: ${socketConnected ? 'Активно' : 'Неактивно'}

=== ЛОГ ОБРАБОТКИ ===

`;

    const fullLogContent = header + logContent;

    // Создаем и скачиваем файл
    const blob = new Blob([fullLogContent], { type: 'text/plain;charset=utf-8' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.style.display = 'none';
    a.href = url;
    a.download = `slowdown_log_${Date.now()}.txt`;
    document.body.appendChild(a);
    a.click();
    window.URL.revokeObjectURL(url);
    document.body.removeChild(a);

    addToLog('📄 Лог сохранен в файл', 'success');
  };

  const testConnection = async () => {
    setMessage('🔄 Проверка подключения к серверу...');
    setMessageType('info');
    await checkBackendHealth();
  };

  return (
    <div className="container">
      <div className="header">
        <h1>SETINA Slowdown App</h1>
        <p>Профессиональное замедление аудио с использованием Rubber Band алгоритма</p>
        
        <div className="backend-status">
          <div className={`status-indicator ${backendStatus}`}>
            <span className="status-dot"></span>
            {backendStatus === 'connected' && 'Сервер подключен'}
            {backendStatus === 'error' && 'Сервер недоступен'}
            {backendStatus === 'checking' && 'Проверка подключения...'}
          </div>
          {backendStatus === 'error' && (
            <button onClick={testConnection} className="test-connection-btn">
              Проверить подключение
            </button>
          )}
        </div>
      </div>

      <div className="upload-section">
        <h2>Загрузка файлов</h2>
        <div 
          className={`file-upload-area ${backendStatus !== 'connected' ? 'disabled' : ''} ${dragActive ? 'drag-active' : ''}`}
          onClick={() => backendStatus === 'connected' && fileInputRef.current?.click()}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept=".mp3,.wav,audio/mp3,audio/wav,audio/mpeg,audio/x-wav"
            onChange={handleFileSelect}
            className="file-input-hidden"
            disabled={backendStatus !== 'connected'}
          />
          <div className="upload-icon">
            🎵
          </div>
          <div className="upload-text">
            <h3>Перетащите файлы сюда или нажмите для выбора</h3>
            <p>Поддерживаются MP3 и WAV файлы</p>
          </div>
        </div>

        {files.length > 0 && (
          <div className="file-list">
            <h3>Выбранные файлы ({files.length})</h3>
            {files.map(file => (
              <div key={file.id} className="file-item">
                <div className="file-info">
                  <div className="file-name">{file.name}</div>
                  <div className="file-size">{formatFileSize(file.size)}</div>
                </div>
                <div className="file-controls">
                  <div className="file-speed-control">
                    <label>Скорость: {file.speed}x</label>
                    <input
                      type="range"
                      min="0.1"
                      max="2.0"
                      step="0.05"
                      value={file.speed}
                      onChange={(e) => updateFileSpeed(file.id, e.target.value)}
                      className="speed-slider file-speed-slider"
                      disabled={processing}
                    />
                  </div>
                  <button
                    onClick={() => removeFile(file.id)}
                    className="remove-btn"
                    disabled={processing}
                  >
                    Удалить
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="settings-section">
        <h2>Настройки</h2>
        <div className="settings-row">
          <label>Глобальная скорость: {globalSpeed}x</label>
          <div className="slider-container">
            <input
              type="range"
              min="0.1"
              max="2.0"
              step="0.05"
              value={globalSpeed}
              onChange={(e) => setGlobalSpeed(parseFloat(e.target.value))}
              className="speed-slider global-speed-slider"
              disabled={processing}
            />
            <div className="slider-labels">
              <span>0.1x</span>
              <span>1.0x</span>
              <span>2.0x</span>
            </div>
          </div>
          <button 
            onClick={applyGlobalSpeed} 
            className="apply-global-btn"
            disabled={processing || files.length === 0}
          >
            Применить ко всем
          </button>
        </div>
        <div className="settings-row">
          <label>Сохранить тональность:</label>
          <div className="checkbox-container">
            <input
              type="checkbox"
              checked={preservePitch}
              onChange={(e) => setPreservePitch(e.target.checked)}
              disabled={processing}
            />
            <span>{preservePitch ? 'Да (Rubber Band)' : 'Нет (простое изменение)'}</span>
          </div>
        </div>
        <div className="settings-row">
          <label>Формат выходного файла:</label>
          <div className="radio-container">
            <label className="radio-option">
              <input
                type="radio"
                name="outputFormat"
                value="wav"
                checked={outputFormat === 'wav'}
                onChange={(e) => setOutputFormat(e.target.value)}
                disabled={processing}
              />
              <span>WAV (без потерь)</span>
            </label>
            <label className="radio-option">
              <input
                type="radio"
                name="outputFormat"
                value="mp3"
                checked={outputFormat === 'mp3'}
                onChange={(e) => setOutputFormat(e.target.value)}
                disabled={processing}
              />
              <span>MP3 (сжатый)</span>
            </label>
          </div>
        </div>
        <div className="settings-row">
          <label>Сохранить лог обработки:</label>
          <div className="checkbox-container">
            <input
              type="checkbox"
              checked={saveLog}
              onChange={(e) => setSaveLog(e.target.checked)}
              disabled={processing}
            />
            <span>{saveLog ? 'Да (автоматически скачается)' : 'Нет'}</span>
          </div>
        </div>
        <p style={{ fontSize: '14px', color: '#666', marginTop: '10px' }}>
          * Значение скорости меньше 1.0 замедляет аудио, больше 1.0 - ускоряет<br/>
          * Rubber Band обеспечивает профессиональное качество обработки
        </p>
      </div>

      <div className="process-section">
        <button
          onClick={processFiles}
          disabled={processing || files.length === 0 || backendStatus !== 'connected'}
          className="process-btn"
        >
          {getProcessButtonText()}
        </button>

        {processing && (
          <div className="progress-container">
            <div className="progress-info">
              <div className="current-file">{currentFile || 'Подготовка к обработке...'}</div>
              <div className="progress-bar">
                <div 
                  className="progress-fill" 
                  style={{ width: `${progress}%` }}
                ></div>
              </div>
              <div className="progress-text">{Math.round(progress)}%</div>
            </div>
            
            {processingLog.length > 0 && (
              <div className="processing-log">
                <div className="log-header">
                  <h4>Лог обработки</h4>
                  <div className="log-buttons">
                    <button onClick={downloadLog} className="download-log-btn">📄 Скачать лог</button>
                    <button onClick={clearLog} className="clear-log-btn">Очистить</button>
                  </div>
                </div>
                <div className="log-content">
                  {processingLog.slice(-10).map(entry => (
                    <div key={entry.id} className={`log-entry log-${entry.type}`}>
                      <span className="log-time">{entry.timestamp}</span>
                      <span className="log-message">{entry.message}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {message && (
          <div className={`message ${messageType === 'error' ? 'error-message' : messageType === 'success' ? 'success-message' : 'info-message'}`}>
            {message}
          </div>
        )}
      </div>

      {backendStatus === 'error' && (
        <div className="backend-instructions">
          <h3>🐍 Инструкции по запуску Python сервера:</h3>
          <div className="code-block">
            <code>
              cd backend<br/>
              pip install -r requirements.txt<br/>
              python app.py
            </code>
          </div>
          <p>После запуска сервер будет доступен на http://localhost:5230</p>
        </div>
      )}
    </div>
  );
}

export default App;
