import React, { useState, useRef } from 'react';
import JSZip from 'jszip';
import { saveAs } from 'file-saver';

function App() {
  const [files, setFiles] = useState([]);
  const [globalSpeed, setGlobalSpeed] = useState(0.5);
  const [preservePitch, setPreservePitch] = useState(true);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [message, setMessage] = useState('');
  const [messageType, setMessageType] = useState('');
  const fileInputRef = useRef(null);

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

  const processAudioFile = async (fileData, speed, preservePitch) => {
    return new Promise((resolve, reject) => {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const fileReader = new FileReader();

      fileReader.onload = async (e) => {
        try {
          const arrayBuffer = e.target.result;
          const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
          
          let processedBuffer;
          
          if (preservePitch) {
            processedBuffer = await processWithPitchPreservation(audioBuffer, speed, audioContext);
          } else {
            processedBuffer = await processWithoutPitchPreservation(audioBuffer, speed, audioContext);
          }

          // Convert to WAV format
          const wavBuffer = audioBufferToWav(processedBuffer);
          resolve(wavBuffer);
        } catch (error) {
          reject(error);
        }
      };

      fileReader.onerror = () => reject(new Error('Ошибка чтения файла'));
      fileReader.readAsArrayBuffer(fileData.file);
    });
  };

  const processWithoutPitchPreservation = async (audioBuffer, speed, audioContext) => {
    const sampleRate = audioBuffer.sampleRate;
    const numberOfChannels = audioBuffer.numberOfChannels;
    const newLength = Math.floor(audioBuffer.length / speed);
    
    const newAudioBuffer = audioContext.createBuffer(
      numberOfChannels,
      newLength,
      sampleRate
    );

    for (let channel = 0; channel < numberOfChannels; channel++) {
      const inputData = audioBuffer.getChannelData(channel);
      const outputData = newAudioBuffer.getChannelData(channel);
      
      for (let i = 0; i < newLength; i++) {
        const sourceIndex = i * speed;
        const index = Math.floor(sourceIndex);
        const fraction = sourceIndex - index;
        
        if (index + 1 < inputData.length) {
          outputData[i] = inputData[index] * (1 - fraction) + inputData[index + 1] * fraction;
        } else if (index < inputData.length) {
          outputData[i] = inputData[index];
        }
      }
    }

    return newAudioBuffer;
  };

  const processWithPitchPreservation = async (audioBuffer, speed, audioContext) => {
    const sampleRate = audioBuffer.sampleRate;
    const numberOfChannels = audioBuffer.numberOfChannels;
    const inputLength = audioBuffer.length;
    const outputLength = Math.floor(inputLength / speed);
    
    // Создаем новый буфер для результата
    const newAudioBuffer = audioContext.createBuffer(
      numberOfChannels,
      outputLength,
      sampleRate
    );

    // Параметры для улучшенного алгоритма
    const frameSize = 2048; // Фиксированный размер для лучшего качества
    const hopAnalysis = Math.floor(frameSize / 4); // Шаг анализа
    const hopSynthesis = Math.floor(hopAnalysis / speed); // Шаг синтеза

    for (let channel = 0; channel < numberOfChannels; channel++) {
      const inputData = audioBuffer.getChannelData(channel);
      const outputData = newAudioBuffer.getChannelData(channel);
      
      // Создаем окно Хэннинга
      const window = new Float32Array(frameSize);
      for (let i = 0; i < frameSize; i++) {
        window[i] = 0.5 * (1 - Math.cos(2 * Math.PI * i / (frameSize - 1)));
      }

      // Буферы для FFT (упрощенная реализация)
      const grainBuffer = new Float32Array(frameSize);
      let inputPos = 0;
      let outputPos = 0;

      while (inputPos + frameSize < inputLength && outputPos + frameSize < outputLength) {
        // Извлекаем зерно (grain) из входного сигнала
        for (let i = 0; i < frameSize; i++) {
          grainBuffer[i] = inputData[inputPos + i] * window[i];
        }

        // Применяем сглаживание для уменьшения артефактов
        const smoothedGrain = applySmoothingFilter(grainBuffer);

        // Добавляем обработанное зерно к выходному сигналу
        for (let i = 0; i < frameSize; i++) {
          if (outputPos + i < outputLength) {
            outputData[outputPos + i] += smoothedGrain[i] * window[i];
          }
        }

        // Перемещаем позиции
        inputPos += hopAnalysis;
        outputPos += hopSynthesis;
      }

      // Нормализация с более мягким ограничением
      normalizeAudioData(outputData);
    }

    return newAudioBuffer;
  };

  // Функция сглаживающего фильтра для уменьшения артефактов
  const applySmoothingFilter = (buffer) => {
    const smoothed = new Float32Array(buffer.length);
    const filterSize = 3;
    
    for (let i = 0; i < buffer.length; i++) {
      let sum = 0;
      let count = 0;
      
      for (let j = -filterSize; j <= filterSize; j++) {
        const index = i + j;
        if (index >= 0 && index < buffer.length) {
          sum += buffer[index];
          count++;
        }
      }
      
      smoothed[i] = sum / count;
    }
    
    return smoothed;
  };

  // Улучшенная функция нормализации
  const normalizeAudioData = (data) => {
    // Находим RMS (среднеквадратичное значение) для более качественной нормализации
    let rms = 0;
    for (let i = 0; i < data.length; i++) {
      rms += data[i] * data[i];
    }
    rms = Math.sqrt(rms / data.length);

    // Находим пиковое значение
    let peak = 0;
    for (let i = 0; i < data.length; i++) {
      peak = Math.max(peak, Math.abs(data[i]));
    }

    // Применяем нормализацию с учетом как RMS, так и пикового значения
    if (peak > 0.95) {
      const normalizationFactor = 0.85 / peak;
      for (let i = 0; i < data.length; i++) {
        data[i] *= normalizationFactor;
      }
    } else if (rms > 0 && rms < 0.1) {
      // Усиливаем слишком тихий сигнал
      const amplificationFactor = Math.min(2.0, 0.3 / rms);
      for (let i = 0; i < data.length; i++) {
        data[i] *= amplificationFactor;
      }
    }
  };

  const audioBufferToWav = (buffer) => {
    const length = buffer.length;
    const numberOfChannels = buffer.numberOfChannels;
    const sampleRate = buffer.sampleRate;
    const arrayBuffer = new ArrayBuffer(44 + length * numberOfChannels * 2);
    const view = new DataView(arrayBuffer);

    // WAV header
    const writeString = (offset, string) => {
      for (let i = 0; i < string.length; i++) {
        view.setUint8(offset + i, string.charCodeAt(i));
      }
    };

    writeString(0, 'RIFF');
    view.setUint32(4, 36 + length * numberOfChannels * 2, true);
    writeString(8, 'WAVE');
    writeString(12, 'fmt ');
    view.setUint32(16, 16, true);
    view.setUint16(20, 1, true);
    view.setUint16(22, numberOfChannels, true);
    view.setUint32(24, sampleRate, true);
    view.setUint32(28, sampleRate * numberOfChannels * 2, true);
    view.setUint16(32, numberOfChannels * 2, true);
    view.setUint16(34, 16, true);
    writeString(36, 'data');
    view.setUint32(40, length * numberOfChannels * 2, true);

    // Convert float samples to 16-bit PCM
    let offset = 44;
    for (let i = 0; i < length; i++) {
      for (let channel = 0; channel < numberOfChannels; channel++) {
        const sample = Math.max(-1, Math.min(1, buffer.getChannelData(channel)[i]));
        view.setInt16(offset, sample * 0x7FFF, true);
        offset += 2;
      }
    }

    return arrayBuffer;
  };

  const processFiles = async () => {
    if (files.length === 0) {
      setMessage('Пожалуйста, выберите файлы для обработки');
      setMessageType('error');
      setTimeout(() => setMessage(''), 3000);
      return;
    }

    setProcessing(true);
    setProgress(0);
    setMessage('');

    try {
      const zip = new JSZip();
      const totalFiles = files.length;

      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        setMessage(`Обработка файла ${i + 1} из ${totalFiles}: ${file.name}`);
        
        try {
          const processedBuffer = await processAudioFile(file, file.speed, preservePitch);
          const fileName = file.name.replace(/\.[^/.]+$/, '') + '_slowed.wav';
          zip.file(fileName, processedBuffer);
        } catch (error) {
          console.error(`Ошибка обработки файла ${file.name}:`, error);
          setMessage(`Ошибка обработки файла ${file.name}: ${error.message}`);
          setMessageType('error');
        }

        setProgress(((i + 1) / totalFiles) * 100);
      }

      setMessage('Создание архива...');
      const zipBlob = await zip.generateAsync({ type: 'blob' });
      saveAs(zipBlob, 'slowed_audio_files.zip');

      setMessage('Обработка завершена! Архив загружен.');
      setMessageType('success');
    } catch (error) {
      setMessage(`Ошибка обработки: ${error.message}`);
      setMessageType('error');
    } finally {
      setProcessing(false);
      setTimeout(() => {
        setMessage('');
        setProgress(0);
      }, 3000);
    }
  };

  return (
    <div className="container">
      <div className="header">
        <h1>SETINA Slowdown App</h1>
        <p>Замедлите ваши аудиофайлы с сохранением или изменением тональности</p>
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
                  />
                  <button
                    onClick={() => removeFile(file.id)}
                    className="remove-btn"
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
          />
          <button onClick={applyGlobalSpeed} className="apply-global-btn">
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
            />
            <span>{preservePitch ? 'Да' : 'Нет'}</span>
          </div>
        </div>
        <p style={{ fontSize: '14px', color: '#666', marginTop: '10px' }}>
          * Значение скорости меньше 1.0 замедляет аудио, больше 1.0 - ускоряет
        </p>
      </div>

      <div className="process-section">
        <button
          onClick={processFiles}
          disabled={processing || files.length === 0}
          className="process-btn"
        >
          {processing ? 'Обработка...' : 'Замедлить'}
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
          <div className={messageType === 'error' ? 'error-message' : 'success-message'}>
            {message}
          </div>
        )}
      </div>
    </div>
  );
}

export default App;
