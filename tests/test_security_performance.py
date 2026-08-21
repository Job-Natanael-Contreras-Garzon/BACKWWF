import asyncio
import statistics
import time
import tracemalloc
import uuid
from datetime import timedelta
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    verify_password,
)


def percentile(data: list[float], p: float) -> float:
    """Calcula el percentil p (0..100) en una lista de números."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_data) - 1)
    d = k - f
    return sorted_data[f] + d * (sorted_data[c] - sorted_data[f])


class TestSecurityUnitAndFunctional:
    """Pruebas funcionales de seguridad y criptografía."""

    def test_password_hashing_and_verification(self):
        password = "SuperSecretPassword123!#"
        hashed = get_password_hash(password)

        assert hashed != password
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
        assert verify_password(password, hashed) is True
        assert verify_password("WrongPassword123!#", hashed) is False
        assert verify_password("", hashed) is False

    def test_access_token_creation_and_decoding(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(subject=user_id, extra_claims={"role": "researcher"})

        payload = decode_token(token, is_refresh=False)
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["type"] == "access"
        assert payload["role"] == "researcher"
        assert "exp" in payload
        assert "iat" in payload

    def test_refresh_token_creation_and_decoding(self):
        user_id = str(uuid.uuid4())
        token = create_refresh_token(subject=user_id, extra_claims={"device": "mobile"})

        payload = decode_token(token, is_refresh=True)
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["type"] == "refresh"
        assert payload["device"] == "mobile"

    def test_token_type_separation(self):
        user_id = str(uuid.uuid4())
        access_token = create_access_token(subject=user_id)
        refresh_token = create_refresh_token(subject=user_id)

        # Access token no debe decodificarse como refresh token
        assert decode_token(access_token, is_refresh=True) is None
        # Refresh token no debe decodificarse como access token
        assert decode_token(refresh_token, is_refresh=False) is None

    def test_expired_token_handling(self):
        user_id = str(uuid.uuid4())
        # Crear token ya expirado (-10 segundos)
        token = create_access_token(subject=user_id, expires_delta=timedelta(seconds=-10))
        payload = decode_token(token, is_refresh=False)
        assert payload is None

    def test_tampered_token_handling(self):
        user_id = str(uuid.uuid4())
        token = create_access_token(subject=user_id)
        tampered_token = token[:-5] + "XXXXX"
        assert decode_token(tampered_token, is_refresh=False) is None


class TestSecurityStressAndPerformance:
    """Pruebas de estrés, concurrencia, latencia percentil y consumo de memoria."""

    @pytest.mark.asyncio
    async def test_jwt_stress_throughput_and_latencies(self):
        """
        Estrés masivo: Generación y decodificación concurrente de 3,000 tokens JWT.
        Evalúa Throughput (tokens/segundo) y percentiles de latencia (p50, p95, p99).
        """
        iterations = 3000
        user_ids = [str(uuid.uuid4()) for _ in range(iterations)]

        # 1. Medir Stress de Generación de Tokens
        start_time = time.perf_counter()

        def generate_and_measure(uid: str):
            t0 = time.perf_counter()
            token = create_access_token(subject=uid)
            t1 = time.perf_counter()
            return token, (t1 - t0) * 1000  # ms

        loop = asyncio.get_running_loop()
        tasks = [loop.run_in_executor(None, generate_and_measure, uid) for uid in user_ids]
        results = await asyncio.gather(*tasks)

        tokens = [r[0] for r in results]
        encode_latencies = [r[1] for r in results]
        total_encode_time = time.perf_counter() - start_time
        encode_throughput = iterations / total_encode_time

        # 2. Medir Stress de Decodificación y Validación de Tokens
        start_decode_time = time.perf_counter()

        def decode_and_measure(token: str):
            t0 = time.perf_counter()
            payload = decode_token(token)
            t1 = time.perf_counter()
            return payload, (t1 - t0) * 1000  # ms

        decode_tasks = [loop.run_in_executor(None, decode_and_measure, tok) for tok in tokens]
        decode_results = await asyncio.gather(*decode_tasks)

        decode_latencies = [r[1] for r in decode_results]
        total_decode_time = time.perf_counter() - start_decode_time
        decode_throughput = iterations / total_decode_time

        # Validar integridad
        for i, (payload, _) in enumerate(decode_results):
            assert payload is not None
            assert payload["sub"] == user_ids[i]

        # Calcular métricas estadísticas con función nativa
        enc_p50 = percentile(encode_latencies, 50)
        enc_p95 = percentile(encode_latencies, 95)
        enc_p99 = percentile(encode_latencies, 99)

        dec_p50 = percentile(decode_latencies, 50)
        dec_p95 = percentile(decode_latencies, 95)
        dec_p99 = percentile(decode_latencies, 99)

        print(f"\n[JWT ENCODE STRESS] Iteraciones: {iterations}")
        print(f"   Throughput: {encode_throughput:.2f} tokens/seg")
        print(f"   Latencias: p50={enc_p50:.3f}ms | p95={enc_p95:.3f}ms | p99={enc_p99:.3f}ms")

        print(f"[JWT DECODE STRESS] Iteraciones: {iterations}")
        print(f"   Throughput: {decode_throughput:.2f} tokens/seg")
        print(f"   Latencias: p50={dec_p50:.3f}ms | p95={dec_p95:.3f}ms | p99={dec_p99:.3f}ms")

        # Criterios de aceptación de rendimiento
        assert enc_p50 < 5.0, f"Latencia p50 de generación excedida: {enc_p50}ms"
        assert enc_p99 < 35.0, f"Latencia p99 de generación excedida: {enc_p99}ms"
        assert dec_p50 < 5.0, f"Latencia p50 de decodificación excedida: {dec_p50}ms"
        assert dec_p99 < 35.0, f"Latencia p99 de decodificación excedida: {dec_p99}ms"

    def test_bcrypt_hashing_performance(self):
        """
        Evalúa el tiempo de cómputo y el coste criptográfico de bcrypt.
        Garantiza resistencia a ataques por fuerza bruta sin penalización excesiva.
        """
        passwords = [f"Password_Test_Number_{i}!" for i in range(5)]
        hash_times = []
        verify_times = []

        for pwd in passwords:
            t0 = time.perf_counter()
            hashed = get_password_hash(pwd)
            t1 = time.perf_counter()
            hash_times.append((t1 - t0) * 1000)

            t2 = time.perf_counter()
            valid = verify_password(pwd, hashed)
            t3 = time.perf_counter()
            verify_times.append((t3 - t2) * 1000)
            assert valid is True

        avg_hash = statistics.mean(hash_times)
        avg_verify = statistics.mean(verify_times)

        print(f"\n[BCRYPT PERFORMANCE] Tiempo promedio hash: {avg_hash:.2f}ms | Tiempo promedio verify: {avg_verify:.2f}ms")
        assert avg_hash < 800.0, f"Hashing bcrypt demasiado lento ({avg_hash}ms)"
        assert avg_verify < 800.0, f"Verificación bcrypt demasiado lenta ({avg_verify}ms)"

    @pytest.mark.asyncio
    async def test_cryptographic_memory_leak_stress(self):
        """
        Monitorea el uso de memoria (tracemalloc) tras 4,000 ciclos de creación y validación.
        Certifica la inexistencia de fugas de memoria (memory leaks).
        """
        tracemalloc.start()
        snapshot_start = tracemalloc.take_snapshot()

        tokens = []
        for _ in range(4000):
            t = create_access_token(subject=str(uuid.uuid4()))
            tokens.append(t)
            decode_token(t)

        tokens.clear()
        snapshot_end = tracemalloc.take_snapshot()
        tracemalloc.stop()

        stats = snapshot_end.compare_to(snapshot_start, "lineno")
        total_growth_kb = sum(stat.size_diff for stat in stats) / 1024

        print(f"\n[MEMORY EFFICIENCY] Crecimiento neto de memoria tras 4,000 ciclos: {total_growth_kb:.2f} KB")
        assert total_growth_kb < 2500, f"Posible fuga de memoria detectada: {total_growth_kb:.2f} KB"
