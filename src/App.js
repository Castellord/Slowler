import React, { useState, useRef } from 'react';

function App() {
  const [files, setFiles] = useState([]);
  const [globalSpeed, setGlobalSpeed] = useState(0.5);
  const [preservePitch, setPreservePitch] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('');
  const [backendStatus, setBackendStatus] = useState('checking');
  const fileInputRef = useRef(null);

  // Проверяем статус бекенда при загрузке
  React.useEffect(() => {
    checkBackendHealth();
  }, []);

  const checkBackendHealth = async () => {
    try {
      const response = await fetch('http://localhost:5000/health');
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

  const handleFileSelect = (event) => {
    const selectedFiles = Array.from(event.target.files);
    const audioFiles = selectedFiles.filter(file => 
      file.type === 'audio/mp3' || file.type === 'audio/wav' || 
      file.type === 'audio/mpeg' || file.type === 'audio/x-wav'
    );

    if (audioFiles.length !== selectedFiles.length) {
      setMessage('Некоторые файлы были пропущены. Поддерживаются только MP3 и WAV файлы.');
      setMessageType('error');
      setTimeout(() => setMessage(''), 3000);
    }

    const newFiles = audioFiles.map((file, index) => ({
      id: Date.now() + index,
      file: file,
      name: file.name,
      size: file.size,
      speed: 0.5
    }));

    setFiles(prev => [...prev, ...newFiles]);
    event.target.value = '';
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
    setMessage('Отправка файлов на сервер обработки...');

    try {
      // Создаем FormData для отправки файлов
      const formData = new FormData();
      
      // Добавляем файлы
      files.forEach((fileData, index) => {
        formData.append('files', fileData.file);
        formData.append('speeds', fileData.speed.toString());
      });
      
      // Добавляем настройки
      formData.append('preserve_pitch', preservePitch.toString());

      setMessage('🔄 Обработка файлов на сервере...');
      setProgress(50);

      // Отправляем запрос на сервер
      const response = await fetch('http://localhost:5000/process', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.error || 'Ошибка сервера');
      }

      setMessage('📦 Получение обработанных файлов...');
      setProgress(90);

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
      setMessage('✅ Обработка завершена! Архив загружен.');
      setMessageType('success');

    } catch (error) {
      console.error('Ошибка обработки:', error);
      setMessage(`❌ Ошибка обработки: ${error.message}`);
      setMessageType('error');
    } finally {
      setProcessing(false);
      setTimeout(() => {
        setMessage('');
        setProgress(0);
      }, 5000);
    }
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
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".mp3,.wav,audio/mp3,audio/wav,audio/mpeg,audio/x-wav"
          onChange={handleFileSelect}
          className="file-input"
          disabled={backendStatus !== 'connected'}
        />
        <p>Выберите MP3 или WAV файлы для обработки</p>

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
                  <label>Скорость:</label>
                  <input
                    type="number"
                    min="0.1"
                    max="2.0"
                    step="0.1"
                    value={file.speed}
                    onChange={(e) => updateFileSpeed(file.id, e.target.value)}
                    className="speed-input"
                    disabled={processing}
                  />
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
          <label>Глобальная скорость:</label>
          <input
            type="number"
            min="0.1"
            max="2.0"
            step="0.1"
            value={globalSpeed}
            onChange={(e) => setGlobalSpeed(parseFloat(e.target.value))}
            className="global-speed-input"
            disabled={processing}
          />
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
          {processing ? 'Обработка на сервере...' : 'Замедлить с Rubber Band'}
        </button>

        {processing && (
          <div className="progress-container">
            <div className="progress-bar">
              <div 
                className="progress-fill" 
                style={{ width: `${progress}%` }}
              ></div>
            </div>
            <div className="progress-text">{Math.round(progress)}%</div>
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
          <p>После запуска сервер будет доступен на http://localhost:5000</p>
        </div>
      )}
    </div>
  );
}

export default App;
