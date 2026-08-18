# 🔐 Endpoints de Autenticación (`/auth`)

Módulo para registro, inicio de sesión y gestión de tokens JWT (Access Token y Refresh Token).

---

## 1. Registro de Usuario
- **Ruta:** `POST /auth/register`
- **Autenticación:** Pública

### Request Body `UserRegister`
```json
{
  "full_name": "María Rodríguez",
  "email": "maria.rodriguez@wwf.org",
  "password": "PasswordSeguro123!",
  "institucion": "WWF Colombia",
  "sexo": "F"
}
```

### Response (`201 Created`)
```json
{
  "status": "success",
  "data": {
    "user": {
      "id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
      "full_name": "María Rodríguez",
      "email": "maria.rodriguez@wwf.org",
      "institucion": "WWF Colombia",
      "sexo": "F",
      "created_at": "2026-08-18T00:00:00Z"
    },
    "tokens": {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "token_type": "bearer"
    }
  },
  "message": "Usuario registrado exitosamente"
}
```

---

## 2. Iniciar Sesión (Login)
- **Ruta:** `POST /auth/login`
- **Autenticación:** Pública

### Request Body `LoginRequest`
```json
{
  "email": "maria.rodriguez@wwf.org",
  "password": "PasswordSeguro123!"
}
```

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "user": {
      "id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
      "full_name": "María Rodríguez",
      "email": "maria.rodriguez@wwf.org"
    },
    "tokens": {
      "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "token_type": "bearer"
    }
  },
  "message": "Autenticación exitosa"
}
```

---

## 3. Renovar Token (Refresh Token)
- **Ruta:** `POST /auth/refresh`
- **Autenticación:** Requiere `refresh_token`

### Request Body `RefreshTokenRequest`
```json
{
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
  },
  "message": "Tokens renovados exitosamente"
}
```

---

## 4. Perfil del Usuario Autenticado
- **Ruta:** `GET /auth/me`
- **Autenticación:** Requiere Header `Authorization: Bearer <access_token>`

### Response (`200 OK`)
```json
{
  "status": "success",
  "data": {
    "id": "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11",
    "full_name": "María Rodríguez",
    "email": "maria.rodriguez@wwf.org",
    "institucion": "WWF Colombia",
    "sexo": "F",
    "is_active": true,
    "created_at": "2026-08-18T00:00:00Z"
  },
  "message": "Perfil de usuario obtenido"
}
```
