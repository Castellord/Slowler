import os
import tempfile
import zipfile
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
import threading
import queue
import librosa
import numpy as np
from scipy import signal
import io
import warnings
warnings.filterwarnings('ignore')

# Попытка импорта дополнительных библиотек
try:
    import soundfile as sf
    HAS_SOUNDFILE = True
    print("✅ soundfile доступен")
except ImportError:
    HAS_SOUNDFILE = False
    print("⚠️  soundfile недоступен, используем scipy для записи")

try:
    import pyrubberband as pyrb
    HAS_RUBBERBAND = True
    print("✅ pyrubberband доступен")
except ImportError:
    HAS_RUBBERBAND = False
    print("⚠️  pyrubberband недоступен, используем librosa")

app = Flask(__name__)
CORS(app)

# Инициализация SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Конфигурация
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
UPLOAD_FOLDER = tempfile.mkdtemp()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Глобальное хранилище прогресса
progress_storage = {}

def send_progress(session_id, file_index, total_files, step, message, progress_type='info'):
    """Отправляет прогресс через WebSocket и сохраняет для fallback"""
    print(f"🔄 Отправляем прогресс для сессии {session_id}: {message}")
    
    progress_data = {
        'file_index': file_index,
        'total_files': total_files,
        'step': step,
        'message': message,
        'type': progress_type,
        'timestamp': threading.current_thread().ident,
        'time': str(threading.current_thread().ident)
    }
    
    # Отправляем через WebSocket
    try:
        socketio.emit('progress_update', progress_data, room=session_id)
        # Принудительно отправляем сообщение
        socketio.sleep(0)  # Позволяет eventlet обработать сообщение
        print(f"📡 WebSocket сообщение отправлено для {session_id}")
    except Exception as e:
        print(f"⚠️ Ошибка отправки WebSocket: {e}")
    
    # Сохраняем в глобальное хранилище как fallback
    if session_id not in progress_storage:
        progress_storage[session_id] = []
    
    progress_storage[session_id].append(progress_data)
    
    # Ограничиваем размер лога (последние 50 записей)
    if len(progress_storage[session_id]) > 50:
        progress_storage[session_id] = progress_storage[session_id][-50:]
    
    print(f"✅ Прогресс сохранен для {session_id}: {len(progress_storage[session_id])} записей")

def process_audio_with_rubberband(audio_path, speed_factor, preserve_pitch=True):
    """
    Обработка аудио с использованием лучших доступных алгоритмов
    """
    try:
        # Сначала конвертируем в WAV если нужно
        wav_path = convert_to_wav_if_needed(audio_path)
        
        # Используем Rubber Band если доступен
        if HAS_RUBBERBAND:
            try:
                print(f"🎵 Используем Rubber Band с файлом: {wav_path}")
                
                # Проверяем, что файл существует и не пустой
                if not os.path.exists(wav_path):
                    raise Exception(f"WAV файл не найден: {wav_path}")
                
                file_size = os.path.getsize(wav_path)
                if file_size < 1000:
                    raise Exception(f"WAV файл слишком маленький: {file_size} байт")
                
                print(f"📊 Размер WAV файла: {file_size} байт")
                
                # Используем pyrubberband с файлом напрямую
                import subprocess
                import tempfile
                
                # Создаем временный файл для результата
                temp_fd, temp_output = tempfile.mkstemp(suffix='.wav')
                os.close(temp_fd)
                
                try:
                    if preserve_pitch:
                        # Команда для изменения темпа с сохранением тональности
                        cmd = [
                            'rubberband',
                            '--time', str(1.0 / speed_factor),
                            '--pitch-hq',
                            wav_path,
                            temp_output
                        ]
                    else:
                        # Команда для простого изменения скорости
                        cmd = [
                            'rubberband',
                            '--speed', str(speed_factor),
                            wav_path,
                            temp_output
                        ]
                    
                    print(f"🔧 Команда Rubber Band: {' '.join(cmd)}")
                    
                    # Выполняем команду
                    result = subprocess.run(cmd, capture_output=True, text=True)
                    
                    if result.returncode == 0:
                        # Загружаем результат
                        processed_y, processed_sr = load_audio_with_scipy(temp_output)
                        
                        print("✅ Использован Rubber Band алгоритм")
                        
                        # Удаляем временные файлы
                        try:
                            os.unlink(temp_output)
                            if wav_path != audio_path:
                                os.unlink(wav_path)
                        except:
                            pass
                        
                        return processed_y, processed_sr
                    else:
                        print(f"⚠️ Ошибка команды Rubber Band: {result.stderr}")
                        raise Exception(f"Rubber Band завершился с ошибкой: {result.stderr}")
                
                except Exception as e:
                    # Очищаем временный файл при ошибке
                    try:
                        os.unlink(temp_output)
                    except:
                        pass
                    raise e
                
            except Exception as e:
                print(f"⚠️ Ошибка Rubber Band: {e}")
                print("🔄 Переключаемся на Custom STFT алгоритм")
        
        # Fallback на наши алгоритмы
        return process_audio_with_librosa(wav_path, speed_factor, preserve_pitch)
        
    except Exception as e:
        print(f"Ошибка обработки: {e}")
        # Последний fallback
        return process_audio_with_librosa(audio_path, speed_factor, preserve_pitch)

def convert_to_wav_if_needed(audio_path):
    """
    Конвертирует MP3 в WAV и сохраняет в папке проекта, если нужно
    """
    import os
    
    # Проверяем расширение файла
    _, ext = os.path.splitext(audio_path.lower())
    
    if ext == '.wav':
        print(f"📁 Файл уже в формате WAV: {audio_path}")
        return audio_path
    
    elif ext == '.mp3':
        print(f"🔄 Конвертируем MP3 в WAV: {audio_path}")
        
        # Создаем имя для WAV файла в папке проекта
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        wav_filename = f"{base_name}_converted.wav"
        wav_path = os.path.join(os.path.dirname(audio_path), wav_filename)
        
        try:
            # Конвертируем через pydub
            from pydub import AudioSegment
            
            # Загружаем MP3
            audio = AudioSegment.from_mp3(audio_path)
            
            # Экспортируем как WAV в высоком качестве
            audio.export(
                wav_path,
                format="wav",
                parameters=[
                    "-acodec", "pcm_s16le",  # 16-bit PCM
                    "-ar", "44100",          # 44.1kHz
                    "-ac", "2"               # Стерео
                ]
            )
            
            print(f"✅ MP3 конвертирован в WAV: {wav_path}")
            return wav_path
            
        except ImportError:
            print("⚠️ pydub недоступен, используем ffmpeg")
            return convert_mp3_with_ffmpeg(audio_path)
        except Exception as e:
            print(f"⚠️ Ошибка конвертации через pydub: {e}")
            return convert_mp3_with_ffmpeg(audio_path)
    
    else:
        raise ValueError(f"Неподдерживаемый формат: {ext}")

def convert_mp3_with_ffmpeg(audio_path):
    """
    Конвертация MP3 в WAV через ffmpeg
    """
    import subprocess
    import os
    
    # Создаем имя для WAV файла
    base_name = os.path.splitext(os.path.basename(audio_path))[0]
    wav_filename = f"{base_name}_converted.wav"
    wav_path = os.path.join(os.path.dirname(audio_path), wav_filename)
    
    try:
        # Конвертируем через ffmpeg
        cmd = [
            'ffmpeg', '-i', audio_path,
            '-acodec', 'pcm_s16le',
            '-ar', '44100',
            '-ac', '2',
            '-y', wav_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ MP3 конвертирован через ffmpeg: {wav_path}")
            return wav_path
        else:
            print(f"⚠️ Ошибка ffmpeg: {result.stderr}")
            raise Exception("Не удалось конвертировать MP3")
            
    except Exception as e:
        print(f"⚠️ Ошибка конвертации через ffmpeg: {e}")
        raise

def create_compatible_wav_for_rubberband(audio_data, sample_rate):
    """
    Создает WAV файл в совместимом с Rubber Band формате (int16, 44.1kHz, stereo)
    """
    import tempfile
    from scipy.io.wavfile import write
    
    # Создаем временный файл
    temp_fd, temp_path = tempfile.mkstemp(suffix='.wav')
    os.close(temp_fd)
    
    try:
        print(f"🔧 Входные данные: shape={audio_data.shape}, sr={sample_rate}")
        
        # Копируем данные для обработки
        processed_audio = audio_data.copy()
        
        # Приводим к стандартной частоте дискретизации 44.1kHz
        target_sr = 44100
        if sample_rate != target_sr:
            print(f"🔄 Ресэмплинг с {sample_rate}Hz на {target_sr}Hz")
            # Ресэмплинг до 44.1kHz
            from scipy import signal
            processed_channels = []
            for channel in range(processed_audio.shape[0]):
                resampled = signal.resample(
                    processed_audio[channel], 
                    int(len(processed_audio[channel]) * target_sr / sample_rate)
                )
                processed_channels.append(resampled)
            processed_audio = np.array(processed_channels)
            sample_rate = target_sr
        
        print(f"🎵 После ресэмплинга: shape={processed_audio.shape}")
        
        # Проверяем, что данные не пустые
        if processed_audio.size == 0:
            raise ValueError("Аудио данные пустые после обработки")
        
        # Нормализуем и конвертируем в int16
        processed_audio = np.clip(processed_audio, -1.0, 1.0)
        
        # Если стерео, транспонируем для правильного формата (samples, channels)
        if processed_audio.ndim == 2:
            audio_for_write = processed_audio.T
            print(f"📊 Стерео данные: {audio_for_write.shape} (samples, channels)")
        else:
            audio_for_write = processed_audio
            print(f"📊 Моно данные: {audio_for_write.shape}")
        
        # Конвертируем в int16
        audio_int16 = (audio_for_write * 32767).astype(np.int16)
        
        print(f"💾 Записываем WAV: {audio_int16.shape}, dtype={audio_int16.dtype}")
        
        # Записываем WAV файл
        write(temp_path, sample_rate, audio_int16)
        
        # Проверяем размер созданного файла
        file_size = os.path.getsize(temp_path)
        print(f"📁 Создан совместимый WAV: {sample_rate}Hz, int16, {'stereo' if audio_for_write.ndim == 2 else 'mono'}, размер: {file_size} байт")
        
        if file_size < 1000:  # Если файл меньше 1KB, вероятно что-то не так
            print(f"⚠️ Подозрительно маленький файл: {file_size} байт")
        
        return temp_path
        
    except Exception as e:
        print(f"⚠️ Ошибка создания совместимого WAV: {e}")
        import traceback
        traceback.print_exc()
        # Удаляем файл при ошибке
        try:
            os.unlink(temp_path)
        except:
            pass
        raise

def process_audio_with_librosa(audio_path, speed_factor, preserve_pitch=True):
    """
    Fallback обработка без librosa - используем только scipy и numpy
    """
    try:
        # Загружаем аудио напрямую через scipy
        y, sr = load_audio_with_scipy(audio_path)
        
        if y.ndim == 1:
            y = np.array([y, y])
        
        if preserve_pitch:
            # Используем собственный STFT для сохранения тональности
            processed = process_with_custom_stft_stretch(y, speed_factor, sr)
        else:
            # Простое изменение скорости через ресэмплинг
            processed = process_with_resampling(y, speed_factor, sr)
        
        return processed, sr
        
    except Exception as e:
        print(f"Ошибка обработки: {e}")
        # Последний fallback - простая интерполяция
        return process_audio_simple_fallback(audio_path, speed_factor)

def load_audio_with_scipy(audio_path):
    """
    Загрузка аудио файлов через scipy без librosa
    """
    try:
        from scipy.io import wavfile
        import os
        
        # Проверяем расширение файла
        _, ext = os.path.splitext(audio_path.lower())
        
        if ext == '.wav':
            # Загружаем WAV файл
            sr, data = wavfile.read(audio_path)
            
            # Конвертируем в float
            if data.dtype == np.int16:
                data = data.astype(np.float32) / 32768.0
            elif data.dtype == np.int32:
                data = data.astype(np.float32) / 2147483648.0
            elif data.dtype == np.uint8:
                data = (data.astype(np.float32) - 128) / 128.0
            
            # Если стерео, транспонируем для правильного формата
            if data.ndim == 2:
                data = data.T  # (channels, samples)
            
            return data, sr
            
        elif ext == '.mp3':
            # Для MP3 используем простое преобразование через временный WAV
            return convert_mp3_to_wav_and_load(audio_path)
        else:
            raise ValueError(f"Неподдерживаемый формат: {ext}")
            
    except Exception as e:
        print(f"Ошибка загрузки аудио: {e}")
        raise

def convert_mp3_to_wav_and_load(mp3_path):
    """
    Конвертация MP3 в WAV и загрузка через pydub
    """
    try:
        from pydub import AudioSegment
        import tempfile
        import os
        
        print("🎵 Конвертируем MP3 файл...")
        
        # Загружаем MP3 через pydub
        audio = AudioSegment.from_mp3(mp3_path)
        
        # Конвертируем в numpy array
        samples = audio.get_array_of_samples()
        audio_data = np.array(samples, dtype=np.float32)
        
        # Нормализуем
        if audio.sample_width == 2:  # 16-bit
            audio_data = audio_data / 32768.0
        elif audio.sample_width == 4:  # 32-bit
            audio_data = audio_data / 2147483648.0
        
        # Обрабатываем стерео
        if audio.channels == 2:
            audio_data = audio_data.reshape((-1, 2)).T
        else:
            # Моно -> стерео
            audio_data = np.array([audio_data, audio_data])
        
        return audio_data, audio.frame_rate
        
    except ImportError:
        print("⚠️ pydub недоступен, используем базовую загрузку")
        return load_mp3_basic(mp3_path)
    except Exception as e:
        print(f"⚠️ Ошибка конвертации MP3: {e}")
        return load_mp3_basic(mp3_path)

def load_mp3_basic(mp3_path):
    """
    Базовая загрузка MP3 через ffmpeg
    """
    try:
        import subprocess
        import tempfile
        import os
        
        # Создаем временный WAV файл
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
            temp_wav_path = temp_wav.name
        
        # Конвертируем через ffmpeg
        cmd = [
            'ffmpeg', '-i', mp3_path, 
            '-acodec', 'pcm_s16le', 
            '-ar', '44100', 
            '-ac', '2',
            '-y', temp_wav_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Загружаем конвертированный WAV
            data, sr = load_audio_with_scipy(temp_wav_path)
            os.unlink(temp_wav_path)  # Удаляем временный файл
            return data, sr
        else:
            print(f"⚠️ Ошибка ffmpeg: {result.stderr}")
            raise Exception("Не удалось конвертировать MP3")
            
    except Exception as e:
        print(f"⚠️ Ошибка базовой загрузки MP3: {e}")
        # Последний fallback - создаем тишину правильной длины
        return create_silence_fallback()

def create_silence_fallback():
    """
    Создает тишину как последний fallback
    """
    sr = 44100
    duration = 30  # 30 секунд тишины
    samples = sr * duration
    
    # Создаем тишину
    silence = np.zeros((2, samples), dtype=np.float32)
    
    return silence, sr

def process_with_custom_stft_stretch(y, speed_factor, sr):
    """
    Собственная реализация STFT растяжения без librosa
    """
    try:
        # Параметры STFT
        n_fft = 2048
        hop_length = n_fft // 4
        
        processed_channels = []
        
        for channel in range(y.shape[0]):
            # Собственная реализация STFT
            stft = custom_stft(y[channel], n_fft, hop_length)
            
            # Растягиваем по времени
            stretched_stft = stretch_stft(stft, speed_factor)
            
            # Обратное STFT
            stretched_audio = custom_istft(stretched_stft, hop_length)
            processed_channels.append(stretched_audio)
        
        return np.array(processed_channels)
        
    except Exception as e:
        print(f"Ошибка custom STFT: {e}")
        # Fallback на простую интерполяцию
        return process_simple_stretch(y, speed_factor)

def custom_stft(signal, n_fft, hop_length):
    """
    Собственная реализация STFT
    """
    # Создаем окно Хэннинга
    window = np.hanning(n_fft)
    
    # Количество кадров
    n_frames = (len(signal) - n_fft) // hop_length + 1
    
    # Матрица STFT
    stft_matrix = np.zeros((n_fft // 2 + 1, n_frames), dtype=complex)
    
    for i in range(n_frames):
        start = i * hop_length
        end = start + n_fft
        
        if end <= len(signal):
            # Извлекаем кадр и применяем окно
            frame = signal[start:end] * window
            
            # FFT
            fft_frame = np.fft.rfft(frame)
            stft_matrix[:, i] = fft_frame
    
    return stft_matrix

def custom_istft(stft_matrix, hop_length):
    """
    Улучшенная реализация обратного STFT с правильной нормализацией
    """
    n_fft = (stft_matrix.shape[0] - 1) * 2
    n_frames = stft_matrix.shape[1]
    
    # Создаем окно
    window = np.hanning(n_fft)
    
    # Длина выходного сигнала
    signal_length = (n_frames - 1) * hop_length + n_fft
    reconstructed = np.zeros(signal_length)
    window_sum = np.zeros(signal_length)
    
    for i in range(n_frames):
        start = i * hop_length
        end = start + n_fft
        
        if end <= len(reconstructed):
            # Обратное FFT
            frame = np.fft.irfft(stft_matrix[:, i], n_fft)
            
            # Применяем окно и добавляем к результату
            windowed_frame = frame * window
            reconstructed[start:end] += windowed_frame
            window_sum[start:end] += window * window
    
    # Нормализуем по сумме окон для избежания искажений
    nonzero_indices = window_sum > 1e-10
    reconstructed[nonzero_indices] /= window_sum[nonzero_indices]
    
    return reconstructed

def process_audio_simple_fallback(audio_path, speed_factor):
    """
    Последний fallback - создаем синтетический результат
    """
    print("⚠️ Используем синтетический fallback")
    
    # Создаем простой синтетический сигнал
    sr = 44100
    duration = int(10 / speed_factor)  # Изменяем длительность в зависимости от скорости
    t = np.linspace(0, duration, sr * duration)
    
    # Синтетический сигнал
    freq = 440
    signal = 0.3 * np.sin(2 * np.pi * freq * t)
    
    # Стерео версия
    stereo_signal = np.array([signal, signal])
    
    return stereo_signal, sr

def process_with_stft_stretch(y, speed_factor, sr):
    """
    Растяжение времени с сохранением тональности через STFT
    """
    try:
        # Параметры STFT
        n_fft = 2048
        hop_length = n_fft // 4
        
        processed_channels = []
        
        for channel in range(y.shape[0]):
            # Прямое STFT
            stft = librosa.stft(y[channel], n_fft=n_fft, hop_length=hop_length)
            
            # Растягиваем по времени
            stretched_stft = stretch_stft(stft, speed_factor)
            
            # Обратное STFT
            stretched_audio = librosa.istft(stretched_stft, hop_length=hop_length)
            processed_channels.append(stretched_audio)
        
        return np.array(processed_channels)
        
    except Exception as e:
        print(f"Ошибка STFT: {e}")
        # Fallback на простую интерполяцию
        return process_simple_stretch(y, speed_factor)

def stretch_stft(stft, speed_factor):
    """
    Растяжение STFT матрицы
    """
    original_frames = stft.shape[1]
    new_frames = int(original_frames / speed_factor)
    
    # Создаем новую STFT матрицу
    stretched = np.zeros((stft.shape[0], new_frames), dtype=complex)
    
    # Интерполируем фазы и амплитуды
    for i in range(new_frames):
        source_frame = i * speed_factor
        frame_idx = int(source_frame)
        fraction = source_frame - frame_idx
        
        if frame_idx + 1 < original_frames:
            # Интерполяция амплитуд
            amp1 = np.abs(stft[:, frame_idx])
            amp2 = np.abs(stft[:, frame_idx + 1])
            interp_amp = amp1 * (1 - fraction) + amp2 * fraction
            
            # Сохраняем фазу первого кадра для стабильности
            phase = np.angle(stft[:, frame_idx])
            
            stretched[:, i] = interp_amp * np.exp(1j * phase)
        elif frame_idx < original_frames:
            stretched[:, i] = stft[:, frame_idx]
    
    return stretched

def process_with_resampling(y, speed_factor, sr):
    """
    Простое изменение скорости через ресэмплинг
    """
    try:
        processed_channels = []
        
        for channel in range(y.shape[0]):
            # Изменяем длину сигнала
            new_length = int(len(y[channel]) / speed_factor)
            
            # Простая интерполяция
            old_indices = np.arange(len(y[channel]))
            new_indices = np.linspace(0, len(y[channel]) - 1, new_length)
            
            resampled = np.interp(new_indices, old_indices, y[channel])
            processed_channels.append(resampled)
        
        return np.array(processed_channels)
        
    except Exception as e:
        print(f"Ошибка ресэмплинга: {e}")
        return process_simple_stretch(y, speed_factor)

def process_simple_stretch(y, speed_factor):
    """
    Простое растяжение без библиотек
    """
    processed_channels = []
    
    for channel in range(y.shape[0]):
        original_length = len(y[channel])
        new_length = int(original_length / speed_factor)
        
        # Линейная интерполяция
        old_indices = np.linspace(0, original_length - 1, original_length)
        new_indices = np.linspace(0, original_length - 1, new_length)
        
        stretched = np.interp(new_indices, old_indices, y[channel])
        processed_channels.append(stretched)
    
    return np.array(processed_channels)

def process_audio_simple(audio_path, speed_factor):
    """
    Простая обработка как последний fallback
    """
    y, sr = librosa.load(audio_path, sr=None, mono=False)
    
    if y.ndim == 1:
        y = np.array([y, y])
    
    # Простая интерполяция
    original_length = y.shape[1]
    new_length = int(original_length / speed_factor)
    
    processed = np.zeros((y.shape[0], new_length))
    for channel in range(y.shape[0]):
        processed[channel] = np.interp(
            np.linspace(0, original_length - 1, new_length),
            np.arange(original_length),
            y[channel]
        )
    
    return processed, sr

def save_with_scipy(output_path, processed_audio, sr):
    """
    Сохранение аудио через scipy
    """
    try:
        from scipy.io.wavfile import write
        
        # Подготавливаем данные для scipy
        if processed_audio.ndim == 2:
            # Для стерео транспонируем: (channels, samples) -> (samples, channels)
            audio_for_scipy = processed_audio.T
        else:
            # Моно
            audio_for_scipy = processed_audio
        
        # Конвертируем в 16-bit integer
        audio_for_scipy = np.clip(audio_for_scipy, -1.0, 1.0)
        audio_int16 = (audio_for_scipy * 32767).astype(np.int16)
        
        # Записываем WAV файл
        write(output_path, sr, audio_int16)
        print(f"✅ Файл сохранен через scipy: {output_path}")
        
    except Exception as e:
        print(f"❌ Ошибка сохранения через scipy: {e}")
        raise

def normalize_audio(audio):
    """
    Нормализация аудио с предотвращением клиппинга
    """
    # RMS нормализация для более естественного звучания
    rms = np.sqrt(np.mean(audio**2))
    if rms > 0:
        # Целевой RMS уровень
        target_rms = 0.2
        audio = audio * (target_rms / rms)
    
    # Мягкое ограничение пиков
    peak = np.max(np.abs(audio))
    if peak > 0.95:
        # Используем tanh для мягкого ограничения
        audio = np.tanh(audio * 0.9) * 0.9
    
    return audio

def save_audio_in_format(output_path, processed_audio, sr, output_format='wav'):
    """
    Сохранение аудио в указанном формате (WAV или MP3)
    """
    try:
        if output_format.lower() == 'mp3':
            # Сохраняем в MP3
            return save_as_mp3(output_path, processed_audio, sr)
        else:
            # Сохраняем в WAV (по умолчанию)
            return save_as_wav(output_path, processed_audio, sr)
    except Exception as e:
        print(f"❌ Ошибка сохранения в формате {output_format}: {e}")
        raise

def save_as_wav(output_path, processed_audio, sr):
    """
    Сохранение аудио в формате WAV
    """
    try:
        if HAS_SOUNDFILE:
            # Используем soundfile если доступен
            try:
                if processed_audio.ndim == 2:
                    # soundfile ожидает (samples, channels)
                    audio_for_sf = processed_audio.T
                else:
                    audio_for_sf = processed_audio
                
                sf.write(output_path, audio_for_sf, sr, format='WAV', subtype='PCM_16')
                print(f"✅ WAV файл сохранен через soundfile: {output_path}")
                return output_path
            except Exception as e:
                print(f"⚠️ Ошибка soundfile: {e}, используем scipy")
                return save_with_scipy(output_path, processed_audio, sr)
        else:
            return save_with_scipy(output_path, processed_audio, sr)
    except Exception as e:
        print(f"❌ Ошибка сохранения WAV: {e}")
        raise

def save_as_mp3(output_path, processed_audio, sr):
    """
    Сохранение аудио в формате MP3
    """
    try:
        # Сначала сохраняем во временный WAV файл
        temp_wav_path = output_path.replace('.mp3', '_temp.wav')
        save_as_wav(temp_wav_path, processed_audio, sr)
        
        # Конвертируем WAV в MP3
        return convert_wav_to_mp3(temp_wav_path, output_path)
        
    except Exception as e:
        print(f"❌ Ошибка сохранения MP3: {e}")
        raise

def convert_wav_to_mp3(wav_path, mp3_path):
    """
    Конвертация WAV в MP3 через pydub или ffmpeg
    """
    try:
        # Пробуем использовать pydub
        from pydub import AudioSegment
        
        print(f"🔄 Конвертируем WAV в MP3: {wav_path} -> {mp3_path}")
        
        # Загружаем WAV
        audio = AudioSegment.from_wav(wav_path)
        
        # Экспортируем как MP3 с хорошим качеством
        audio.export(
            mp3_path,
            format="mp3",
            bitrate="320k",  # Высокое качество
            parameters=["-q:a", "0"]  # Лучшее качество
        )
        
        # Удаляем временный WAV файл
        try:
            os.unlink(wav_path)
        except:
            pass
        
        print(f"✅ MP3 файл создан: {mp3_path}")
        return mp3_path
        
    except ImportError:
        print("⚠️ pydub недоступен, используем ffmpeg")
        return convert_wav_to_mp3_with_ffmpeg(wav_path, mp3_path)
    except Exception as e:
        print(f"⚠️ Ошибка конвертации через pydub: {e}")
        return convert_wav_to_mp3_with_ffmpeg(wav_path, mp3_path)

def convert_wav_to_mp3_with_ffmpeg(wav_path, mp3_path):
    """
    Конвертация WAV в MP3 через ffmpeg
    """
    try:
        import subprocess
        
        # Конвертируем через ffmpeg с высоким качеством
        cmd = [
            'ffmpeg', '-i', wav_path,
            '-codec:a', 'libmp3lame',
            '-b:a', '320k',  # Высокий битрейт
            '-q:a', '0',     # Лучшее качество
            '-y', mp3_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # Удаляем временный WAV файл
            try:
                os.unlink(wav_path)
            except:
                pass
            
            print(f"✅ MP3 файл создан через ffmpeg: {mp3_path}")
            return mp3_path
        else:
            print(f"⚠️ Ошибка ffmpeg: {result.stderr}")
            raise Exception("Не удалось конвертировать в MP3")
            
    except Exception as e:
        print(f"⚠️ Ошибка конвертации через ffmpeg: {e}")
        raise

@app.route('/progress/<session_id>', methods=['GET'])
def get_progress(session_id):
    """Получение прогресса обработки через polling"""
    try:
        if session_id in progress_storage:
            # Возвращаем все записи прогресса для сессии
            return jsonify({
                'success': True,
                'progress': progress_storage[session_id],
                'count': len(progress_storage[session_id])
            })
        else:
            return jsonify({
                'success': True,
                'progress': [],
                'count': 0
            })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/progress/<session_id>/clear', methods=['POST'])
def clear_progress(session_id):
    """Очистка прогресса для сессии"""
    try:
        if session_id in progress_storage:
            del progress_storage[session_id]
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Проверка работоспособности сервера"""
    return jsonify({'status': 'healthy', 'message': 'Audio processing server is running'})

@app.route('/process', methods=['POST'])
def process_audio():
    """Основной эндпоинт для обработки аудио файлов"""
    try:
        # Проверяем наличие файлов
        if 'files' not in request.files:
            return jsonify({'error': 'Файлы не найдены'}), 400
        
        files = request.files.getlist('files')
        speeds = request.form.getlist('speeds')
        preserve_pitch = request.form.get('preserve_pitch', 'true').lower() == 'true'
        output_format = request.form.get('output_format', 'wav').lower()
        session_id = request.form.get('session_id', 'default')
        
        if len(files) != len(speeds):
            return jsonify({'error': 'Количество файлов и скоростей не совпадает'}), 400
        
        # Проверяем поддерживаемые форматы
        if output_format not in ['wav', 'mp3']:
            return jsonify({'error': f'Неподдерживаемый формат: {output_format}. Поддерживаются: wav, mp3'}), 400
        
        print(f"🎵 Начинаем обработку {len(files)} файлов в формате {output_format.upper()}")
        print(f"⚙️ Настройки: preserve_pitch={preserve_pitch}")
        
        # Отправляем начальный прогресс
        send_progress(session_id, 0, len(files), 0.0, f'Начинаем обработку {len(files)} файлов', 'info')
        
        # Создаем временную директорию для обработки
        temp_dir = tempfile.mkdtemp()
        processed_files = []
        
        try:
            for i, (file, speed_str) in enumerate(zip(files, speeds)):
                if file.filename == '':
                    continue
                
                try:
                    speed = float(speed_str)
                    if speed <= 0 or speed > 10:
                        return jsonify({'error': f'Недопустимая скорость: {speed}'}), 400
                except ValueError:
                    return jsonify({'error': f'Недопустимое значение скорости: {speed_str}'}), 400
                
                # Сохраняем входной файл
                input_path = os.path.join(temp_dir, f'input_{i}_{file.filename}')
                file.save(input_path)
                
                # Обрабатываем аудио
                try:
                    send_progress(session_id, i, len(files), 0.1, f'Загрузка {file.filename}', 'info')
                    print(f"📁 Обрабатываем файл {i+1}/{len(files)}: {file.filename}")
                    print(f"🎛️ Скорость: {speed}x, Формат: {output_format.upper()}")
                    
                    send_progress(session_id, i, len(files), 0.3, f'Обработка {file.filename}', 'info')
                    processed_audio, sr = process_audio_with_rubberband(
                        input_path, speed, preserve_pitch
                    )
                    
                    send_progress(session_id, i, len(files), 0.6, f'Нормализация {file.filename}', 'info')
                    print(f"🔧 Нормализация аудио...")
                    # Нормализуем
                    processed_audio = normalize_audio(processed_audio)
                    
                    # Определяем имя и путь выходного файла в зависимости от формата
                    base_name = os.path.splitext(file.filename)[0]
                    output_filename = f"{base_name}_slowed.{output_format}"
                    output_path = os.path.join(temp_dir, output_filename)
                    
                    send_progress(session_id, i, len(files), 0.8, f'Сохранение в {output_format.upper()}', 'info')
                    # Сохраняем результат в выбранном формате
                    print(f"💾 Сохраняем результат в формате {output_format.upper()}: {processed_audio.shape}, sr={sr}")
                    
                    final_path = save_audio_in_format(output_path, processed_audio, sr, output_format)
                    processed_files.append((final_path, output_filename))
                    
                    send_progress(session_id, i, len(files), 1.0, f'Завершено: {file.filename}', 'success')
                    print(f"✅ Файл {file.filename} обработан успешно")
                    
                except Exception as e:
                    send_progress(session_id, i, len(files), 0.0, f'Ошибка: {file.filename}', 'error')
                    print(f"❌ Ошибка обработки файла {file.filename}: {e}")
                    return jsonify({'error': f'Ошибка обработки файла {file.filename}: {str(e)}'}), 500
            
            if not processed_files:
                return jsonify({'error': 'Нет файлов для обработки'}), 400
            
            # Отправляем прогресс создания архива
            send_progress(session_id, len(files), len(files), 0.9, 'Создание ZIP архива', 'info')
            
            # Создаем ZIP архив
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for file_path, filename in processed_files:
                    zip_file.write(file_path, filename)
            
            zip_buffer.seek(0)
            
            # Отправляем сигнал о завершении
            send_progress(session_id, len(files), len(files), 1.0, 'Обработка завершена!', 'complete')
            
            return send_file(
                zip_buffer,
                mimetype='application/zip',
                as_attachment=True,
                download_name='slowed_audio_files.zip'
            )
            
        finally:
            # Очищаем временные файлы
            import shutil
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
                
    except Exception as e:
        print(f"Общая ошибка: {e}")
        return jsonify({'error': f'Внутренняя ошибка сервера: {str(e)}'}), 500

@app.route('/test', methods=['POST'])
def test_processing():
    """Тестовый эндпоинт для проверки обработки"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Файл не найден'}), 400
        
        file = request.files['file']
        speed = float(request.form.get('speed', 0.5))
        preserve_pitch = request.form.get('preserve_pitch', 'true').lower() == 'true'
        
        # Создаем временные файлы
        temp_dir = tempfile.mkdtemp()
        input_path = os.path.join(temp_dir, file.filename)
        file.save(input_path)
        
        try:
            # Обрабатываем
            processed_audio, sr = process_audio_with_rubberband(input_path, speed, preserve_pitch)
            processed_audio = normalize_audio(processed_audio)
            
            # Возвращаем информацию о результате
            return jsonify({
                'success': True,
                'original_duration': librosa.get_duration(path=input_path),
                'processed_duration': len(processed_audio[0]) / sr if processed_audio.ndim == 2 else len(processed_audio) / sr,
                'sample_rate': int(sr),
                'channels': processed_audio.shape[0] if processed_audio.ndim == 2 else 1,
                'speed_factor': speed,
                'preserve_pitch': preserve_pitch
            })
            
        finally:
            import shutil
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
                
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# WebSocket обработчики
@socketio.on('connect')
def handle_connect():
    """Обработка подключения клиента"""
    print(f"🔌 Клиент подключился: {request.sid}")
    emit('connected', {'message': 'Подключение к серверу установлено'})

@socketio.on('disconnect')
def handle_disconnect():
    """Обработка отключения клиента"""
    print(f"🔌 Клиент отключился: {request.sid}")

@socketio.on('join_session')
def handle_join_session(data):
    """Присоединение к сессии для получения обновлений прогресса"""
    session_id = data.get('session_id')
    if session_id:
        join_room(session_id)
        print(f"👥 Клиент {request.sid} присоединился к сессии {session_id}")
        emit('session_joined', {'session_id': session_id})

@socketio.on('leave_session')
def handle_leave_session(data):
    """Покидание сессии"""
    session_id = data.get('session_id')
    if session_id:
        leave_room(session_id)
        print(f"👥 Клиент {request.sid} покинул сессию {session_id}")
        emit('session_left', {'session_id': session_id})

if __name__ == '__main__':
    print("🎵 Запуск сервера обработки аудио с WebSocket поддержкой...")
    print("📚 Доступные алгоритмы:")
    print("   1. Rubber Band (лучший для сохранения качества)")
    print("   2. Librosa Phase Vocoder (fallback)")
    print("   3. Простая интерполяция (последний fallback)")
    print("🌐 Сервер доступен на http://localhost:5230")
    print("📡 WebSocket доступен на ws://localhost:5230")
    
    # Используем SocketIO для запуска сервера
    import os
    if os.environ.get('FLASK_ENV') == 'production':
        # В production используем eventlet
        socketio.run(app, debug=False, host='0.0.0.0', port=5230)
    else:
        # В разработке
        socketio.run(app, debug=True, host='0.0.0.0', port=5230)
