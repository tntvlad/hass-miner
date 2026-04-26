# Authentication API

## Login

Authenticates a user and returns a token for subsequent requests.

**Endpoint:** `POST /api/v1/auth/login`

**Request Body:**

```json
{
  "username": "root",
  "password": "root"
}
```

**Response (200):**

```json
{
  "token": "XEQclIUShm7QhQzz",
  "timeout_s": 3600
}
```

**Usage:**
Include the token in all subsequent requests:

```
Authorization: Bearer <token>
```

---

## Set Password

Set or remove user password.

**Endpoint:** `PUT /api/v1/auth/password`

**Request Body:**

```json
{
  "password": "newpassword"
}
```

Set `password` to `null` to remove the password.

**Response:** 204 on success
