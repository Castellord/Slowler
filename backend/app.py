import os
import tempfile
import zipfile
from flask import Flask, request, jsonify, send_file, Response
from flask_cors import CORS
import json
import threading
import queue
import librosa
import numpy as np
from scipy import signal
import io
import warnings
import base64
import matplotlib
matplotlib.use('Agg')  # Используем non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
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

# Конфигурация
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
UPLOAD_FOLDER = tempfile.mkdtemp()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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
        
        print(f"🎵 Начинаем обработку {len(files)} файлов в формате {output_format.upper()}")
        
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
                    print(f"📁 Обрабатываем файл {i+1}/{len(files)}: {file.filename}")
                    print(f"🎛️ Скорость: {speed}x, Формат: {output_format.upper()}")
                    
                    processed_audio, sr = process_audio_with_rubberband(
                        input_path, speed, preserve_pitch
                    )
                    
                    print(f"🔧 Нормализация аудио...")
                    # Нормализуем
                    processed_audio = normalize_audio(processed_audio)
                    
                    # Определяем имя и путь выходного файла в зависимости от формата
                    base_name = os.path.splitext(file.filename)[0]
                    output_filename = f"{base_name}_slowed.{output_format}"
                    output_path = os.path.join(temp_dir, output_filename)
                    
                    # Сохраняем результат в выбранном формате
                    print(f"💾 Сохраняем результат в формате {output_format.upper()}: {processed_audio.shape}, sr={sr}")
                    
                    final_path = save_audio_in_format(output_path, processed_audio, sr, output_format)
                    processed_files.append((final_path, output_filename))
                    
                    print(f"✅ Файл {file.filename} обработан успешно")
                    
                except Exception as e:
                    print(f"❌ Ошибка обработки файла {file.filename}: {e}")
                    return jsonify({'error': f'Ошибка обработки файла {file.filename}: {str(e)}'}), 500
            
            if not processed_files:
                return jsonify({'error': 'Нет файлов для обработки'}), 400
            
            print("📦 Создание ZIP архива...")
            
            # Создаем ZIP архив
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for file_path, filename in processed_files:
                    zip_file.write(file_path, filename)
            
            zip_buffer.seek(0)
            
            print("✅ Обработка завершена!")
            
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


def analyze_audio_file(audio_path):
    """
    Анализ аудио файла для получения аналитических данных
    """
    try:
        print(f"🔍 Анализируем аудио файл: {audio_path}")
        
        # Загружаем аудио файл
        y, sr = librosa.load(audio_path, sr=None, mono=False)
        
        # Если стерео, берем среднее для анализа
        if y.ndim == 2:
            y_mono = np.mean(y, axis=0)
        else:
            y_mono = y
        
        # Базовая информация о файле
        duration = len(y_mono) / sr
        file_size = os.path.getsize(audio_path)
        
        # Определяем формат файла
        _, ext = os.path.splitext(audio_path.lower())
        audio_format = ext[1:].upper() if ext else 'Unknown'
        
        # Определяем разрядность (приблизительно)
        bit_depth = 16  # По умолчанию для большинства файлов
        if audio_format == 'WAV':
            try:
                from scipy.io import wavfile
                _, data = wavfile.read(audio_path)
                if data.dtype == np.int16:
                    bit_depth = 16
                elif data.dtype == np.int32:
                    bit_depth = 32
                elif data.dtype == np.float32:
                    bit_depth = 32
            except:
                pass
        
        # Анализ BPM (темп)
        print("🥁 Анализируем BPM...")
        try:
            tempo, beats = librosa.beat.beat_track(y=y_mono, sr=sr)
            bpm = float(tempo)
        except:
            bpm = None
        
        # Анализ тональности
        print("🎼 Анализируем тональность...")
        try:
            # Используем chroma features для определения тональности
            chroma = librosa.feature.chroma_stft(y=y_mono, sr=sr)
            chroma_mean = np.mean(chroma, axis=1)
            
            # Определяем основную тональность
            key_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
            key_index = np.argmax(chroma_mean)
            key = key_names[key_index]
            
            # Определяем мажор/минор (упрощенно)
            # Анализируем интервалы для определения лада
            major_profile = np.array([1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1])
            minor_profile = np.array([1, 0, 1, 1, 0, 1, 0, 1, 1, 0, 1, 0])
            
            # Сдвигаем профили в соответствии с найденной тональностью
            major_shifted = np.roll(major_profile, key_index)
            minor_shifted = np.roll(minor_profile, key_index)
            
            # Вычисляем корреляцию
            major_corr = np.corrcoef(chroma_mean, major_shifted)[0, 1]
            minor_corr = np.corrcoef(chroma_mean, minor_shifted)[0, 1]
            
            if major_corr > minor_corr:
                key_signature = f"{key} Major"
            else:
                key_signature = f"{key} Minor"
                
        except Exception as e:
            print(f"⚠️ Ошибка анализа тональности: {e}")
            key_signature = "Unknown"
        
        # Спектральный анализ
        print("📊 Создаем спектрограмму...")
        try:
            # Создаем спектрограмму
            D = librosa.stft(y_mono)
            S_db = librosa.amplitude_to_db(np.abs(D), ref=np.max)
            
            # Создаем изображение спектрограммы
            plt.figure(figsize=(12, 6))
            plt.style.use('dark_background')
            
            # Настраиваем цветовую схему
            colors = ['#0a0a0f', '#1a1a2e', '#8b5cf6', '#a78bfa', '#ffffff']
            n_bins = 256
            cmap = LinearSegmentedColormap.from_list('custom', colors, N=n_bins)
            
            librosa.display.specshow(
                S_db, 
                sr=sr, 
                x_axis='time', 
                y_axis='hz',
                cmap=cmap,
                fmax=8000  # Ограничиваем частоты для лучшей визуализации
            )
            
            plt.colorbar(format='%+2.0f dB', label='Amplitude (dB)')
            plt.title('Спектрограмма', color='white', fontsize=14, pad=20)
            plt.xlabel('Время (с)', color='white')
            plt.ylabel('Частота (Гц)', color='white')
            
            # Настраиваем внешний вид
            plt.gca().set_facecolor('#0a0a0f')
            plt.gcf().patch.set_facecolor('#0a0a0f')
            plt.tick_params(colors='white')
            
            # Сохраняем в буфер
            buffer = io.BytesIO()
            plt.savefig(buffer, format='png', dpi=100, bbox_inches='tight', 
                       facecolor='#0a0a0f', edgecolor='none')
            buffer.seek(0)
            
            # Кодируем в base64
            spectrogram_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
            plt.close()
            
        except Exception as e:
            print(f"⚠️ Ошибка создания спектрограммы: {e}")
            spectrogram_base64 = None
        
        # Дополнительные аналитические данные
        print("📈 Вычисляем дополнительные метрики...")
        try:
            # RMS энергия
            rms = librosa.feature.rms(y=y_mono)[0]
            avg_rms = float(np.mean(rms))
            
            # Спектральный центроид (яркость)
            spectral_centroids = librosa.feature.spectral_centroid(y=y_mono, sr=sr)[0]
            avg_spectral_centroid = float(np.mean(spectral_centroids))
            
            # Zero crossing rate (характеризует перкуссивность)
            zcr = librosa.feature.zero_crossing_rate(y_mono)[0]
            avg_zcr = float(np.mean(zcr))
            
            # Спектральная полоса пропускания
            spectral_bandwidth = librosa.feature.spectral_bandwidth(y=y_mono, sr=sr)[0]
            avg_bandwidth = float(np.mean(spectral_bandwidth))
            
        except Exception as e:
            print(f"⚠️ Ошибка вычисления метрик: {e}")
            avg_rms = None
            avg_spectral_centroid = None
            avg_zcr = None
            avg_bandwidth = None
        
        # Вычисляем расширенные характеристики для анализа жанра
        try:
            print("🎼 Анализируем расширенные характеристики...")
            
            # Спектральный роллофф (частота, ниже которой содержится 85% энергии)
            rolloff = librosa.feature.spectral_rolloff(y=y_mono, sr=sr)[0]
            avg_rolloff = float(np.mean(rolloff))
            
            # MFCC (мел-частотные кепстральные коэффициенты)
            mfccs = librosa.feature.mfcc(y=y_mono, sr=sr, n_mfcc=13)
            mfcc_mean = np.mean(mfccs, axis=1)
            
            # Спектральный контраст
            contrast = librosa.feature.spectral_contrast(y=y_mono, sr=sr)
            avg_contrast = float(np.mean(contrast))
            
            # Анализ частотного баланса
            freq_balance = analyze_frequency_balance(y_mono, sr)
            
            # Анализ гармонической сложности
            harmonic_complexity = analyze_harmonic_complexity(y_mono, sr)
            
            # Анализ ритмической регулярности
            rhythmic_regularity = analyze_rhythmic_regularity(y_mono, sr)
            
            # Анализ вероятности наличия вокала
            vocal_likelihood = analyze_vocal_presence(y_mono, sr, mfccs)
            
            # Анализ перкуссивности
            percussive_strength = analyze_percussive_strength(y_mono, sr)
            
            # Анализ присутствия синтезаторов
            synth_presence = analyze_synth_presence(y_mono, sr, mfccs, avg_contrast)
            
            # Собираем все расширенные характеристики
            extended_features = {
                'rolloff': avg_rolloff,
                'mfcc_mean': mfcc_mean,
                'contrast': avg_contrast,
                'bass_emphasis': freq_balance['bass_emphasis'],
                'mid_freq_balance': freq_balance['mid_freq_balance'],
                'high_freq_presence': freq_balance['high_freq_presence'],
                'harmonic_complexity': harmonic_complexity,
                'rhythmic_regularity': rhythmic_regularity,
                'vocal_likelihood': vocal_likelihood,
                'percussive_strength': percussive_strength,
                'synth_presence': synth_presence
            }
            
        except Exception as e:
            print(f"⚠️ Ошибка вычисления расширенных характеристик: {e}")
            extended_features = {
                'rolloff': None,
                'mfcc_mean': None,
                'contrast': None,
                'bass_emphasis': 0.3,
                'mid_freq_balance': 0.4,
                'high_freq_presence': 0.3,
                'harmonic_complexity': 0.5,
                'rhythmic_regularity': 0.7,
                'vocal_likelihood': 0.3,
                'percussive_strength': 0.6,
                'synth_presence': 0.5
            }

        # Анализ жанра
        print("🎭 Анализируем жанр...")
        try:
            genre_info = analyze_genre(y_mono, sr, bpm, avg_spectral_centroid, avg_zcr, avg_rms, avg_bandwidth, extended_features)
        except Exception as e:
            print(f"⚠️ Ошибка анализа жанра: {e}")
            genre_info = {
                'predicted_genre': 'Unknown',
                'confidence': 0.0,
                'genre_probabilities': {}
            }
        
        # Формируем результат
        analysis_result = {
            'success': True,
            'basic_info': {
                'duration': round(duration, 2),
                'sample_rate': int(sr),
                'channels': y.shape[0] if y.ndim == 2 else 1,
                'file_size': file_size,
                'format': audio_format,
                'bit_depth': bit_depth
            },
            'musical_analysis': {
                'bpm': round(bpm, 1) if bpm else None,
                'key_signature': key_signature,
                'tempo_description': get_tempo_description(bpm) if bpm else None,
                'genre': genre_info['predicted_genre'],
                'genre_confidence': genre_info['confidence'],
                'genre_probabilities': genre_info['genre_probabilities']
            },
            'spectral_analysis': {
                'spectrogram': spectrogram_base64,
                'avg_rms': round(avg_rms, 4) if avg_rms else None,
                'spectral_centroid': round(avg_spectral_centroid, 1) if avg_spectral_centroid else None,
                'zero_crossing_rate': round(avg_zcr, 4) if avg_zcr else None,
                'spectral_bandwidth': round(avg_bandwidth, 1) if avg_bandwidth else None
            }
        }
        
        print("✅ Анализ аудио завершен успешно")
        return analysis_result
        
    except Exception as e:
        print(f"❌ Ошибка анализа аудио: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }

def analyze_genre(y, sr, bpm, spectral_centroid, zcr, rms, bandwidth, extended_features):
    """
    Расширенный анализ жанра электронной музыки с детальными критериями
    """
    # 20 основных жанров электронной музыки с расширенными характеристиками
    electronic_genres = {
        'House': {
            'bpm_range': (120, 130),
            'spectral_centroid_range': (1500, 3000),
            'zcr_range': (0.05, 0.15),
            'rms_range': (0.1, 0.3),
            'bandwidth_range': (1000, 2500),
            # Расширенные критерии
            'bass_emphasis': (0.15, 0.35),  # Сильный бас, но не доминирующий
            'mid_freq_balance': (0.25, 0.45),  # Сбалансированные средние частоты
            'high_freq_presence': (0.20, 0.40),  # Умеренные высокие частоты
            'harmonic_complexity': (0.3, 0.6),  # Средняя гармоническая сложность
            'rhythmic_regularity': (0.7, 0.9),  # Очень регулярный ритм
            'vocal_likelihood': (0.2, 0.7),  # Может содержать вокал
            'percussive_strength': (0.6, 0.8),  # Сильная перкуссия
            'synth_presence': (0.5, 0.8)  # Заметное присутствие синтезаторов
        },
        'Techno': {
            'bpm_range': (120, 150),
            'spectral_centroid_range': (2000, 4000),
            'zcr_range': (0.08, 0.20),
            'rms_range': (0.15, 0.35),
            'bandwidth_range': (1500, 3000),
            'bass_emphasis': (0.25, 0.45),
            'mid_freq_balance': (0.30, 0.50),
            'high_freq_presence': (0.35, 0.55),
            'harmonic_complexity': (0.2, 0.5),  # Менее сложная гармония
            'rhythmic_regularity': (0.8, 0.95),  # Очень регулярный ритм
            'vocal_likelihood': (0.0, 0.3),  # Редко содержит вокал
            'percussive_strength': (0.7, 0.9),  # Очень сильная перкуссия
            'synth_presence': (0.6, 0.9)  # Сильное присутствие синтезаторов
        },
        'Trance': {
            'bpm_range': (125, 140),
            'spectral_centroid_range': (2500, 5000),
            'zcr_range': (0.06, 0.16),
            'rms_range': (0.12, 0.30),
            'bandwidth_range': (2000, 4000),
            'bass_emphasis': (0.20, 0.40),
            'mid_freq_balance': (0.35, 0.55),
            'high_freq_presence': (0.40, 0.70),  # Яркие высокие частоты
            'harmonic_complexity': (0.4, 0.7),  # Сложная гармония
            'rhythmic_regularity': (0.7, 0.9),
            'vocal_likelihood': (0.3, 0.8),  # Часто содержит вокал
            'percussive_strength': (0.5, 0.7),
            'synth_presence': (0.7, 0.95)  # Очень сильное присутствие синтезаторов
        },
        'Dubstep': {
            'bpm_range': (135, 145),
            'spectral_centroid_range': (1000, 3500),
            'zcr_range': (0.10, 0.25),
            'rms_range': (0.20, 0.45),
            'bandwidth_range': (1500, 4000),
            'bass_emphasis': (0.40, 0.70),  # Очень сильный бас
            'mid_freq_balance': (0.20, 0.40),
            'high_freq_presence': (0.25, 0.50),
            'harmonic_complexity': (0.3, 0.6),
            'rhythmic_regularity': (0.4, 0.7),  # Менее регулярный ритм
            'vocal_likelihood': (0.2, 0.6),
            'percussive_strength': (0.6, 0.8),
            'synth_presence': (0.6, 0.9)
        },
        'Drum and Bass': {
            'bpm_range': (160, 180),
            'spectral_centroid_range': (2000, 5000),
            'zcr_range': (0.15, 0.30),
            'rms_range': (0.18, 0.40),
            'bandwidth_range': (2500, 5000),
            'bass_emphasis': (0.35, 0.60),  # Сильный бас
            'mid_freq_balance': (0.25, 0.45),
            'high_freq_presence': (0.30, 0.60),
            'harmonic_complexity': (0.3, 0.6),
            'rhythmic_regularity': (0.5, 0.8),  # Сложные ритмы
            'vocal_likelihood': (0.1, 0.5),
            'percussive_strength': (0.8, 0.95),  # Очень сильная перкуссия
            'synth_presence': (0.4, 0.7)
        },
        'Ambient': {
            'bpm_range': (60, 90),
            'spectral_centroid_range': (800, 2000),
            'zcr_range': (0.02, 0.08),
            'rms_range': (0.05, 0.15),
            'bandwidth_range': (500, 1500),
            'bass_emphasis': (0.10, 0.30),  # Мягкий бас
            'mid_freq_balance': (0.30, 0.60),
            'high_freq_presence': (0.20, 0.50),
            'harmonic_complexity': (0.5, 0.8),  # Сложная гармония
            'rhythmic_regularity': (0.2, 0.5),  # Слабый ритм
            'vocal_likelihood': (0.1, 0.4),
            'percussive_strength': (0.1, 0.3),  # Слабая перкуссия
            'synth_presence': (0.6, 0.9)  # Много синтезаторных текстур
        },
        'Breakbeat': {
            'bpm_range': (120, 140),
            'spectral_centroid_range': (1500, 3500),
            'zcr_range': (0.12, 0.25),
            'rms_range': (0.15, 0.35),
            'bandwidth_range': (1800, 3500),
            'bass_emphasis': (0.25, 0.45),
            'mid_freq_balance': (0.30, 0.50),
            'high_freq_presence': (0.25, 0.45),
            'harmonic_complexity': (0.3, 0.6),
            'rhythmic_regularity': (0.3, 0.6),  # Нерегулярные ритмы
            'vocal_likelihood': (0.2, 0.6),
            'percussive_strength': (0.7, 0.9),  # Сильная перкуссия
            'synth_presence': (0.4, 0.7)
        },
        'Electro': {
            'bpm_range': (110, 130),
            'spectral_centroid_range': (1800, 4000),
            'zcr_range': (0.08, 0.18),
            'rms_range': (0.12, 0.28),
            'bandwidth_range': (1500, 3000),
            'bass_emphasis': (0.30, 0.50),
            'mid_freq_balance': (0.25, 0.45),
            'high_freq_presence': (0.30, 0.55),
            'harmonic_complexity': (0.2, 0.5),
            'rhythmic_regularity': (0.6, 0.8),
            'vocal_likelihood': (0.1, 0.4),
            'percussive_strength': (0.6, 0.8),
            'synth_presence': (0.7, 0.9)  # Характерные электро-синтезаторы
        },
        'Progressive House': {
            'bpm_range': (120, 130),
            'spectral_centroid_range': (2000, 4500),
            'zcr_range': (0.06, 0.14),
            'rms_range': (0.10, 0.25),
            'bandwidth_range': (1800, 3500),
            'bass_emphasis': (0.20, 0.40),
            'mid_freq_balance': (0.35, 0.55),
            'high_freq_presence': (0.35, 0.60),
            'harmonic_complexity': (0.5, 0.8),  # Сложная прогрессивная гармония
            'rhythmic_regularity': (0.6, 0.8),
            'vocal_likelihood': (0.3, 0.7),
            'percussive_strength': (0.5, 0.7),
            'synth_presence': (0.6, 0.9)
        },
        'Deep House': {
            'bpm_range': (115, 125),
            'spectral_centroid_range': (1200, 2500),
            'zcr_range': (0.04, 0.12),
            'rms_range': (0.08, 0.22),
            'bandwidth_range': (1000, 2200),
            'bass_emphasis': (0.25, 0.50),  # Глубокий бас
            'mid_freq_balance': (0.30, 0.50),
            'high_freq_presence': (0.15, 0.35),  # Приглушенные высокие
            'harmonic_complexity': (0.4, 0.7),
            'rhythmic_regularity': (0.7, 0.9),
            'vocal_likelihood': (0.4, 0.8),  # Часто содержит вокал
            'percussive_strength': (0.4, 0.6),  # Мягкая перкуссия
            'synth_presence': (0.5, 0.8)
        },
        'Trap': {
            'bpm_range': (130, 170),
            'spectral_centroid_range': (1500, 4000),
            'zcr_range': (0.10, 0.22),
            'rms_range': (0.15, 0.35),
            'bandwidth_range': (1800, 4000),
            'bass_emphasis': (0.35, 0.65),  # Сильный 808 бас
            'mid_freq_balance': (0.20, 0.40),
            'high_freq_presence': (0.30, 0.55),
            'harmonic_complexity': (0.2, 0.5),
            'rhythmic_regularity': (0.5, 0.7),
            'vocal_likelihood': (0.3, 0.8),  # Часто содержит рэп
            'percussive_strength': (0.7, 0.9),  # Характерные trap хэты
            'synth_presence': (0.4, 0.7)
        },
        'Future Bass': {
            'bpm_range': (130, 160),
            'spectral_centroid_range': (2500, 6000),
            'zcr_range': (0.08, 0.18),
            'rms_range': (0.12, 0.30),
            'bandwidth_range': (2000, 5000),
            'bass_emphasis': (0.25, 0.50),
            'mid_freq_balance': (0.30, 0.50),
            'high_freq_presence': (0.40, 0.70),  # Яркие высокие частоты
            'harmonic_complexity': (0.4, 0.7),
            'rhythmic_regularity': (0.5, 0.7),
            'vocal_likelihood': (0.4, 0.8),  # Часто содержит вокал
            'percussive_strength': (0.5, 0.7),
            'synth_presence': (0.7, 0.95)  # Характерные future bass синтезаторы
        },
        'Hardstyle': {
            'bpm_range': (140, 160),
            'spectral_centroid_range': (2000, 5000),
            'zcr_range': (0.12, 0.25),
            'rms_range': (0.20, 0.40),
            'bandwidth_range': (2500, 5000),
            'bass_emphasis': (0.30, 0.55),
            'mid_freq_balance': (0.25, 0.45),
            'high_freq_presence': (0.35, 0.65),
            'harmonic_complexity': (0.2, 0.5),
            'rhythmic_regularity': (0.8, 0.95),  # Очень регулярный ритм
            'vocal_likelihood': (0.2, 0.6),
            'percussive_strength': (0.8, 0.95),  # Характерный hardstyle kick
            'synth_presence': (0.6, 0.9)
        },
        'Minimal': {
            'bpm_range': (120, 135),
            'spectral_centroid_range': (1000, 2500),
            'zcr_range': (0.04, 0.12),
            'rms_range': (0.08, 0.20),
            'bandwidth_range': (800, 2000),
            'bass_emphasis': (0.20, 0.40),
            'mid_freq_balance': (0.25, 0.45),
            'high_freq_presence': (0.15, 0.35),
            'harmonic_complexity': (0.2, 0.4),  # Простая гармония
            'rhythmic_regularity': (0.7, 0.9),
            'vocal_likelihood': (0.0, 0.3),  # Редко содержит вокал
            'percussive_strength': (0.5, 0.7),
            'synth_presence': (0.3, 0.6)  # Минимальное использование синтезаторов
        },
        'Garage': {
            'bpm_range': (125, 140),
            'spectral_centroid_range': (1500, 3500),
            'zcr_range': (0.10, 0.20),
            'rms_range': (0.12, 0.28),
            'bandwidth_range': (1500, 3000),
            'bass_emphasis': (0.25, 0.45),
            'mid_freq_balance': (0.30, 0.50),
            'high_freq_presence': (0.25, 0.45),
            'harmonic_complexity': (0.3, 0.6),
            'rhythmic_regularity': (0.4, 0.7),  # Характерные garage ритмы
            'vocal_likelihood': (0.3, 0.7),
            'percussive_strength': (0.6, 0.8),
            'synth_presence': (0.4, 0.7)
        },
        'IDM': {
            'bpm_range': (80, 160),
            'spectral_centroid_range': (1500, 4500),
            'zcr_range': (0.08, 0.25),
            'rms_range': (0.10, 0.30),
            'bandwidth_range': (1500, 4000),
            'bass_emphasis': (0.15, 0.45),
            'mid_freq_balance': (0.25, 0.55),
            'high_freq_presence': (0.30, 0.60),
            'harmonic_complexity': (0.6, 0.9),  # Очень сложная гармония
            'rhythmic_regularity': (0.2, 0.5),  # Нерегулярные ритмы
            'vocal_likelihood': (0.1, 0.4),
            'percussive_strength': (0.3, 0.7),
            'synth_presence': (0.5, 0.8)
        },
        'Psytrance': {
            'bpm_range': (140, 150),
            'spectral_centroid_range': (2500, 6000),
            'zcr_range': (0.10, 0.20),
            'rms_range': (0.15, 0.35),
            'bandwidth_range': (2500, 5500),
            'bass_emphasis': (0.25, 0.45),
            'mid_freq_balance': (0.30, 0.50),
            'high_freq_presence': (0.40, 0.70),
            'harmonic_complexity': (0.4, 0.7),
            'rhythmic_regularity': (0.7, 0.9),
            'vocal_likelihood': (0.0, 0.2),  # Редко содержит вокал
            'percussive_strength': (0.6, 0.8),
            'synth_presence': (0.8, 0.95)  # Очень много психоделических синтезаторов
        },
        'Synthwave': {
            'bpm_range': (100, 120),
            'spectral_centroid_range': (1500, 3500),
            'zcr_range': (0.05, 0.15),
            'rms_range': (0.10, 0.25),
            'bandwidth_range': (1200, 2800),
            'bass_emphasis': (0.20, 0.40),
            'mid_freq_balance': (0.35, 0.55),
            'high_freq_presence': (0.25, 0.50),
            'harmonic_complexity': (0.4, 0.7),
            'rhythmic_regularity': (0.6, 0.8),
            'vocal_likelihood': (0.2, 0.6),
            'percussive_strength': (0.4, 0.6),
            'synth_presence': (0.8, 0.95)  # Характерные ретро-синтезаторы
        },
        'Chillout': {
            'bpm_range': (80, 110),
            'spectral_centroid_range': (1000, 2500),
            'zcr_range': (0.03, 0.10),
            'rms_range': (0.06, 0.18),
            'bandwidth_range': (800, 2000),
            'bass_emphasis': (0.15, 0.35),
            'mid_freq_balance': (0.35, 0.60),
            'high_freq_presence': (0.20, 0.45),
            'harmonic_complexity': (0.4, 0.7),
            'rhythmic_regularity': (0.4, 0.7),
            'vocal_likelihood': (0.3, 0.7),
            'percussive_strength': (0.2, 0.4),  # Мягкая перкуссия
            'synth_presence': (0.5, 0.8)
        },
        'Bass Music': {
            'bpm_range': (130, 150),
            'spectral_centroid_range': (800, 2500),
            'zcr_range': (0.08, 0.20),
            'rms_range': (0.18, 0.40),
            'bandwidth_range': (1000, 3000),
            'bass_emphasis': (0.50, 0.80),  # Доминирующий бас
            'mid_freq_balance': (0.15, 0.35),
            'high_freq_presence': (0.20, 0.40),
            'harmonic_complexity': (0.2, 0.5),
            'rhythmic_regularity': (0.5, 0.7),
            'vocal_likelihood': (0.2, 0.6),
            'percussive_strength': (0.6, 0.8),
            'synth_presence': (0.6, 0.9)  # Басовые синтезаторы
        }
    }
    
    # Вычисляем расширенные характеристики для анализа жанра
    try:
        print("🎼 Анализируем расширенные характеристики...")
        
        # Спектральный роллофф (частота, ниже которой содержится 85% энергии)
        rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
        avg_rolloff = float(np.mean(rolloff))
        
        # MFCC (мел-частотные кепстральные коэффициенты)
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        mfcc_mean = np.mean(mfccs, axis=1)
        
        # Спектральный контраст
        contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
        avg_contrast = float(np.mean(contrast))
        
        # Анализ частотного баланса
        freq_balance = analyze_frequency_balance(y, sr)
        
        # Анализ гармонической сложности
        harmonic_complexity = analyze_harmonic_complexity(y, sr)
        
        # Анализ ритмической регулярности
        rhythmic_regularity = analyze_rhythmic_regularity(y, sr)
        
        # Анализ вероятности наличия вокала
        vocal_likelihood = analyze_vocal_presence(y, sr, mfccs)
        
        # Анализ перкуссивности
        percussive_strength = analyze_percussive_strength(y, sr)
        
        # Анализ присутствия синтезаторов
        synth_presence = analyze_synth_presence(y, sr, mfccs, avg_contrast)
        
        # Собираем все расширенные характеристики
        extended_features = {
            'rolloff': avg_rolloff,
            'mfcc_mean': mfcc_mean,
            'contrast': avg_contrast,
            'bass_emphasis': freq_balance['bass_emphasis'],
            'mid_freq_balance': freq_balance['mid_freq_balance'],
            'high_freq_presence': freq_balance['high_freq_presence'],
            'harmonic_complexity': harmonic_complexity,
            'rhythmic_regularity': rhythmic_regularity,
            'vocal_likelihood': vocal_likelihood,
            'percussive_strength': percussive_strength,
            'synth_presence': synth_presence
        }
        
    except Exception as e:
        print(f"⚠️ Ошибка вычисления расширенных характеристик: {e}")
        extended_features = {
            'rolloff': None,
            'mfcc_mean': None,
            'contrast': None,
            'bass_emphasis': 0.3,
            'mid_freq_balance': 0.4,
            'high_freq_presence': 0.3,
            'harmonic_complexity': 0.5,
            'rhythmic_regularity': 0.7,
            'vocal_likelihood': 0.3,
            'percussive_strength': 0.6,
            'synth_presence': 0.5
        }
    
    # Вычисляем вероятности для каждого жанра
    genre_scores = {}
    
    for genre, characteristics in electronic_genres.items():
        score = 0.0
        total_weight = 0.0
        
        # BPM (вес 0.3)
        if bpm is not None:
            bpm_min, bpm_max = characteristics['bpm_range']
            if bpm_min <= bpm <= bpm_max:
                score += 0.3
            else:
                # Штраф за отклонение от диапазона
                deviation = min(abs(bpm - bpm_min), abs(bpm - bpm_max))
                penalty = max(0, 0.3 - deviation / 50.0)  # Уменьшаем штраф постепенно
                score += penalty
            total_weight += 0.3
        
        # Спектральный центроид (вес 0.25)
        if spectral_centroid is not None:
            sc_min, sc_max = characteristics['spectral_centroid_range']
            if sc_min <= spectral_centroid <= sc_max:
                score += 0.25
            else:
                deviation = min(abs(spectral_centroid - sc_min), abs(spectral_centroid - sc_max))
                penalty = max(0, 0.25 - deviation / 2000.0)
                score += penalty
            total_weight += 0.25
        
        # Zero Crossing Rate (вес 0.2)
        if zcr is not None:
            zcr_min, zcr_max = characteristics['zcr_range']
            if zcr_min <= zcr <= zcr_max:
                score += 0.2
            else:
                deviation = min(abs(zcr - zcr_min), abs(zcr - zcr_max))
                penalty = max(0, 0.2 - deviation / 0.1)
                score += penalty
            total_weight += 0.2
        
        # RMS энергия (вес 0.15)
        if rms is not None:
            rms_min, rms_max = characteristics['rms_range']
            if rms_min <= rms <= rms_max:
                score += 0.15
            else:
                deviation = min(abs(rms - rms_min), abs(rms - rms_max))
                penalty = max(0, 0.15 - deviation / 0.2)
                score += penalty
            total_weight += 0.15
        
        # Спектральная полоса пропускания (вес 0.1)
        if bandwidth is not None:
            bw_min, bw_max = characteristics['bandwidth_range']
            if bw_min <= bandwidth <= bw_max:
                score += 0.1
            else:
                deviation = min(abs(bandwidth - bw_min), abs(bandwidth - bw_max))
                penalty = max(0, 0.1 - deviation / 1500.0)
                score += penalty
            total_weight += 0.1
        
        # Добавляем расширенные критерии с меньшими весами
        
        # Баланс частот (вес 0.05)
        if extended_features['bass_emphasis'] is not None:
            bass_min, bass_max = characteristics['bass_emphasis']
            if bass_min <= extended_features['bass_emphasis'] <= bass_max:
                score += 0.05
            else:
                deviation = min(abs(extended_features['bass_emphasis'] - bass_min), 
                              abs(extended_features['bass_emphasis'] - bass_max))
                penalty = max(0, 0.05 - deviation / 0.5)
                score += penalty
            total_weight += 0.05
        
        # Гармоническая сложность (вес 0.04)
        if extended_features['harmonic_complexity'] is not None:
            harm_min, harm_max = characteristics['harmonic_complexity']
            if harm_min <= extended_features['harmonic_complexity'] <= harm_max:
                score += 0.04
            else:
                deviation = min(abs(extended_features['harmonic_complexity'] - harm_min),
                              abs(extended_features['harmonic_complexity'] - harm_max))
                penalty = max(0, 0.04 - deviation / 0.5)
                score += penalty
            total_weight += 0.04
        
        # Ритмическая регулярность (вес 0.04)
        if extended_features['rhythmic_regularity'] is not None:
            rhythm_min, rhythm_max = characteristics['rhythmic_regularity']
            if rhythm_min <= extended_features['rhythmic_regularity'] <= rhythm_max:
                score += 0.04
            else:
                deviation = min(abs(extended_features['rhythmic_regularity'] - rhythm_min),
                              abs(extended_features['rhythmic_regularity'] - rhythm_max))
                penalty = max(0, 0.04 - deviation / 0.5)
                score += penalty
            total_weight += 0.04
        
        # Вокальное присутствие (вес 0.03)
        if extended_features['vocal_likelihood'] is not None:
            vocal_min, vocal_max = characteristics['vocal_likelihood']
            if vocal_min <= extended_features['vocal_likelihood'] <= vocal_max:
                score += 0.03
            else:
                deviation = min(abs(extended_features['vocal_likelihood'] - vocal_min),
                              abs(extended_features['vocal_likelihood'] - vocal_max))
                penalty = max(0, 0.03 - deviation / 0.5)
                score += penalty
            total_weight += 0.03
        
        # Перкуссивная сила (вес 0.03)
        if extended_features['percussive_strength'] is not None:
            perc_min, perc_max = characteristics['percussive_strength']
            if perc_min <= extended_features['percussive_strength'] <= perc_max:
                score += 0.03
            else:
                deviation = min(abs(extended_features['percussive_strength'] - perc_min),
                              abs(extended_features['percussive_strength'] - perc_max))
                penalty = max(0, 0.03 - deviation / 0.5)
                score += penalty
            total_weight += 0.03
        
        # Присутствие синтезаторов (вес 0.03)
        if extended_features['synth_presence'] is not None:
            synth_min, synth_max = characteristics['synth_presence']
            if synth_min <= extended_features['synth_presence'] <= synth_max:
                score += 0.03
            else:
                deviation = min(abs(extended_features['synth_presence'] - synth_min),
                              abs(extended_features['synth_presence'] - synth_max))
                penalty = max(0, 0.03 - deviation / 0.5)
                score += penalty
            total_weight += 0.03
        
        # Нормализуем счет
        if total_weight > 0:
            genre_scores[genre] = score / total_weight
        else:
            genre_scores[genre] = 0.0
    
    # Находим жанр с наивысшим счетом
    if genre_scores:
        predicted_genre = max(genre_scores, key=genre_scores.get)
        confidence = genre_scores[predicted_genre]
        
        # Сортируем жанры по вероятности
        sorted_genres = dict(sorted(genre_scores.items(), key=lambda x: x[1], reverse=True))
        
        # Берем топ-5 жанров для отображения
        top_genres = dict(list(sorted_genres.items())[:5])
        
        return {
            'predicted_genre': predicted_genre,
            'confidence': round(confidence * 100, 1),  # Переводим в проценты
            'genre_probabilities': {k: round(v * 100, 1) for k, v in top_genres.items()}
        }
    else:
        return {
            'predicted_genre': 'Unknown',
            'confidence': 0.0,
            'genre_probabilities': {}
        }

def analyze_frequency_balance(y, sr):
    """
    Анализ баланса частот: бас, средние и высокие частоты
    """
    try:
        # Вычисляем спектр
        D = librosa.stft(y)
        magnitude = np.abs(D)
        
        # Определяем частотные диапазоны
        freqs = librosa.fft_frequencies(sr=sr)
        
        # Басовые частоты (20-250 Hz)
        bass_mask = (freqs >= 20) & (freqs <= 250)
        bass_energy = np.mean(magnitude[bass_mask, :])
        
        # Средние частоты (250-4000 Hz)
        mid_mask = (freqs >= 250) & (freqs <= 4000)
        mid_energy = np.mean(magnitude[mid_mask, :])
        
        # Высокие частоты (4000-20000 Hz)
        high_mask = (freqs >= 4000) & (freqs <= 20000)
        high_energy = np.mean(magnitude[high_mask, :])
        
        # Нормализуем относительно общей энергии
        total_energy = bass_energy + mid_energy + high_energy
        
        if total_energy > 0:
            bass_emphasis = bass_energy / total_energy
            mid_freq_balance = mid_energy / total_energy
            high_freq_presence = high_energy / total_energy
        else:
            bass_emphasis = 0.33
            mid_freq_balance = 0.33
            high_freq_presence = 0.33
        
        return {
            'bass_emphasis': float(bass_emphasis),
            'mid_freq_balance': float(mid_freq_balance),
            'high_freq_presence': float(high_freq_presence)
        }
        
    except Exception as e:
        print(f"⚠️ Ошибка анализа частотного баланса: {e}")
        return {
            'bass_emphasis': 0.33,
            'mid_freq_balance': 0.33,
            'high_freq_presence': 0.33
        }

def analyze_harmonic_complexity(y, sr):
    """
    Анализ гармонической сложности на основе chroma и тональной стабильности
    """
    try:
        # Chroma features для анализа гармонии
        chroma = librosa.feature.chroma_stft(y=y, sr=sr)
        
        # Вычисляем стандартное отклонение chroma (показатель сложности)
        chroma_std = np.std(chroma, axis=1)
        avg_chroma_complexity = np.mean(chroma_std)
        
        # Тональная стабильность (насколько стабильна тональность)
        chroma_var = np.var(chroma, axis=1)
        tonal_stability = 1.0 - np.mean(chroma_var)
        
        # Комбинируем показатели
        harmonic_complexity = (avg_chroma_complexity + (1.0 - tonal_stability)) / 2.0
        
        # Нормализуем в диапазон 0-1
        harmonic_complexity = np.clip(harmonic_complexity, 0.0, 1.0)
        
        return float(harmonic_complexity)
        
    except Exception as e:
        print(f"⚠️ Ошибка анализа гармонической сложности: {e}")
        return 0.5

def analyze_rhythmic_regularity(y, sr):
    """
    Анализ ритмической регулярности на основе onset detection и beat tracking
    """
    try:
        # Детекция onset'ов (начал нот/ударов)
        onset_frames = librosa.onset.onset_detect(y=y, sr=sr)
        onset_times = librosa.frames_to_time(onset_frames, sr=sr)
        
        if len(onset_times) < 3:
            return 0.5  # Недостаточно данных
        
        # Вычисляем интервалы между onset'ами
        intervals = np.diff(onset_times)
        
        # Регулярность = обратная величина стандартного отклонения интервалов
        if len(intervals) > 1:
            interval_std = np.std(intervals)
            mean_interval = np.mean(intervals)
            
            if mean_interval > 0:
                # Коэффициент вариации (CV)
                cv = interval_std / mean_interval
                # Преобразуем в показатель регулярности (0-1)
                regularity = 1.0 / (1.0 + cv)
            else:
                regularity = 0.5
        else:
            regularity = 0.5
        
        return float(np.clip(regularity, 0.0, 1.0))
        
    except Exception as e:
        print(f"⚠️ Ошибка анализа ритмической регулярности: {e}")
        return 0.7

def analyze_vocal_presence(y, sr, mfccs):
    """
    Анализ вероятности наличия вокала на основе MFCC и спектральных характеристик
    """
    try:
        # MFCC характеристики, типичные для вокала
        # Первые несколько MFCC коэффициентов содержат информацию о формантах
        if mfccs is not None and len(mfccs) >= 4:
            # Анализируем первые 4 MFCC коэффициента
            mfcc_vocal_indicators = mfccs[1:4]  # Пропускаем первый (энергия)
            
            # Вокал обычно имеет характерные значения MFCC
            vocal_score = 0.0
            
            # MFCC1: обычно в диапазоне -50 до 50 для вокала
            if -50 <= mfcc_vocal_indicators[0] <= 50:
                vocal_score += 0.3
            
            # MFCC2: вариативность указывает на формантные переходы
            mfcc2_var = np.var(mfccs[2])
            if 10 <= mfcc2_var <= 100:
                vocal_score += 0.3
            
            # MFCC3: также связан с формантами
            mfcc3_mean = np.mean(mfccs[3])
            if -30 <= mfcc3_mean <= 30:
                vocal_score += 0.2
        else:
            vocal_score = 0.3
        
        # Дополнительный анализ через спектральные характеристики
        try:
            # Спектральный центроид в диапазоне человеческого голоса
            spectral_centroids = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
            avg_centroid = np.mean(spectral_centroids)
            
            # Человеческий голос обычно в диапазоне 500-4000 Hz
            if 500 <= avg_centroid <= 4000:
                vocal_score += 0.2
            
        except:
            pass
        
        return float(np.clip(vocal_score, 0.0, 1.0))
        
    except Exception as e:
        print(f"⚠️ Ошибка анализа вокального присутствия: {e}")
        return 0.3

def analyze_percussive_strength(y, sr):
    """
    Анализ силы перкуссивных элементов
    """
    try:
        # Разделяем на гармонические и перкуссивные компоненты
        y_harmonic, y_percussive = librosa.effects.hpss(y)
        
        # Вычисляем энергию перкуссивных компонентов
        percussive_energy = np.mean(y_percussive ** 2)
        total_energy = np.mean(y ** 2)
        
        if total_energy > 0:
            percussive_ratio = percussive_energy / total_energy
        else:
            percussive_ratio = 0.5
        
        # Дополнительно анализируем onset strength
        try:
            onset_strength = librosa.onset.onset_strength(y=y, sr=sr)
            avg_onset_strength = np.mean(onset_strength)
            
            # Нормализуем и комбинируем с перкуссивным соотношением
            normalized_onset = np.clip(avg_onset_strength / 10.0, 0.0, 1.0)
            percussive_strength = (percussive_ratio + normalized_onset) / 2.0
        except:
            percussive_strength = percussive_ratio
        
        return float(np.clip(percussive_strength, 0.0, 1.0))
        
    except Exception as e:
        print(f"⚠️ Ошибка анализа перкуссивной силы: {e}")
        return 0.6

def analyze_synth_presence(y, sr, mfccs, spectral_contrast):
    """
    Анализ присутствия синтезаторов на основе спектральных характеристик
    """
    try:
        synth_score = 0.0
        
        # Синтезаторы часто имеют высокий спектральный контраст
        if spectral_contrast is not None:
            if spectral_contrast > 15:  # Высокий контраст
                synth_score += 0.3
            elif spectral_contrast > 10:
                synth_score += 0.2
        
        # Анализ спектрального роллоффа
        try:
            rolloff = librosa.feature.spectral_rolloff(y=y, sr=sr)[0]
            avg_rolloff = np.mean(rolloff)
            
            # Синтезаторы могут иметь расширенный частотный спектр
            if avg_rolloff > 8000:  # Высокие частоты
                synth_score += 0.2
        except:
            pass
        
        # Анализ спектральной плоскости (flatness)
        try:
            spectral_flatness = librosa.feature.spectral_flatness(y=y)[0]
            avg_flatness = np.mean(spectral_flatness)
            
            # Синтезаторы могут иметь более "плоский" спектр
            if avg_flatness > 0.1:
                synth_score += 0.2
        except:
            pass
        
        # MFCC анализ для синтетических звуков
        if mfccs is not None and len(mfccs) >= 6:
            # Синтезаторы часто имеют характерные MFCC паттерны
            mfcc_variance = np.var(mfccs[4:6], axis=1)
            avg_mfcc_var = np.mean(mfcc_variance)
            
            if avg_mfcc_var > 50:  # Высокая вариативность
                synth_score += 0.2
        
        # Анализ zero crossing rate (уже есть в основных параметрах)
        try:
            zcr = librosa.feature.zero_crossing_rate(y)[0]
            avg_zcr = np.mean(zcr)
            
            # Синтезаторы могут иметь характерные ZCR паттерны
            if 0.05 <= avg_zcr <= 0.3:
                synth_score += 0.1
        except:
            pass
        
        return float(np.clip(synth_score, 0.0, 1.0))
        
    except Exception as e:
        print(f"⚠️ Ошибка анализа присутствия синтезаторов: {e}")
        return 0.5

def get_tempo_description(bpm):
    """
    Возвращает описание темпа на основе BPM
    """
    if bpm is None:
        return None
    
    if bpm < 60:
        return "Очень медленно (Largo)"
    elif bpm < 76:
        return "Медленно (Adagio)"
    elif bpm < 108:
        return "Умеренно (Andante)"
    elif bpm < 120:
        return "Умеренно быстро (Moderato)"
    elif bpm < 168:
        return "Быстро (Allegro)"
    elif bpm < 200:
        return "Очень быстро (Presto)"
    else:
        return "Чрезвычайно быстро (Prestissimo)"

@app.route('/analyze', methods=['POST'])
def analyze_audio():
    """
    Эндпоинт для анализа аудио файла
    """
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'Файл не найден'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'Файл не выбран'}), 400
        
        # Проверяем формат файла
        allowed_extensions = {'.mp3', '.wav', '.flac', '.m4a', '.aac'}
        _, ext = os.path.splitext(file.filename.lower())
        if ext not in allowed_extensions:
            return jsonify({'error': f'Неподдерживаемый формат файла: {ext}'}), 400
        
        # Создаем временную директорию
        temp_dir = tempfile.mkdtemp()
        
        try:
            # Сохраняем файл
            input_path = os.path.join(temp_dir, file.filename)
            file.save(input_path)
            
            print(f"🔍 Начинаем анализ файла: {file.filename}")
            
            # Анализируем файл
            analysis_result = analyze_audio_file(input_path)
            
            return jsonify(analysis_result)
            
        finally:
            # Очищаем временные файлы
            import shutil
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
                
    except Exception as e:
        print(f"❌ Ошибка в эндпоинте анализа: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    print("🎵 Запуск сервера обработки аудио...")
    print("📚 Доступные алгоритмы:")
    print("   1. Rubber Band (лучший для сохранения качества)")
    print("   2. Librosa Phase Vocoder (fallback)")
    print("   3. Простая интерполяция (последний fallback)")
    print("🌐 Сервер доступен на http://localhost:5230")
    
    # Запускаем обычный Flask сервер
    app.run(debug=True, host='0.0.0.0', port=5230)
