# We gonna generate so random keys
import secrets

SECRET_KEY=secrets.token_urlsafe(32)
print(SECRET_KEY)