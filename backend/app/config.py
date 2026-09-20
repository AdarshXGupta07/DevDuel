from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # --- existing, required: the app must refuse to boot without these (ADR-0002) ---
    supabase_url: str
    app_env: str
    jwt_secret: str

    # --- CORS. '*' is only tolerated in development. See ADR-0022. ---
    # Comma-separated in .env, e.g. CORS_ORIGINS=http://localhost:5173,https://devduel.app
    cors_origins: str = "http://localhost:5173"

    # --- tokens ---
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    # --- judge / sandbox (ADR-0020) ---
    judge_image_python: str = "devduel-runner:py312"
    judge_image_node: str = "devduel-runner:node22"
    judge_image_cpp: str = "devduel-runner:cpp13"
    judge_image_java: str = "devduel-runner:java21"
    judge_timeout_seconds: float = 5.0
    judge_memory_mb: int = 256
    judge_cpus: float = 0.5
    judge_pids_limit: int = 64
    judge_max_output_bytes: int = 64 * 1024
    judge_max_concurrent: int = 4

    # --- duel rules ---
    duel_time_limit_seconds: int = 900          # 15 minutes
    countdown_seconds: int = 5
    disconnect_grace_seconds: int = 30          # ADR-0018
    ranked_daily_limit: int = 2                 # free tier
    daily_reset_timezone: str = "Asia/Kolkata"  # fixed IST reset

    # --- proctoring (ADR-0043) ---
    proctor_enabled: bool = True
    # Ranked only by default: casual is where people try the product, and kicking a
    # first-time user for alt-tabbing is a great way to never see them again.
    proctor_ranked_only: bool = True
    # Seconds to come back before the duel is forfeited. 0 = instant kick.
    # Not zero by default because an OS notification steals focus through no fault of
    # the player, and losing a ranked match to a calendar popup is indefensible.
    proctor_grace_seconds: int = 15
    # How many times they may leave and return before it is a forfeit anyway.
    proctor_max_violations: int = 3

    # --- rage-quit deterrent (ADR-0042) ---
    # After this many abandoned duels in one day, matchmaking is blocked for a while.
    abandon_threshold: int = 2
    abandon_cooldown_minutes: int = 15          # doubles per further abandon, capped

    # --- AI features (Anthropic). Empty means the AI endpoints report themselves
    # disabled and the UI hides them, rather than failing at call time. ---
    anthropic_api_key: str = ""
    ai_model: str = "claude-opus-5"
    # Effort trades thoroughness against token spend. A code review is a short,
    # well-specified task, so 'medium' is the sweet spot — 'high' costs more for
    # little gain here. Raise it if review quality disappoints.
    ai_effort: str = "medium"
    ai_max_tokens: int = 4000
    ai_timeout_seconds: float = 90.0

    # --- billing (Razorpay). Empty in dev; the API reports billing as disabled. ---
    razorpay_key_id: str = ""
    razorpay_key_secret: str = ""
    razorpay_webhook_secret: str = ""
    razorpay_plan_id: str = ""
    subscription_amount_paise: int = 5000        # ₹50/month
    subscription_total_count: int = 120          # 10 years of monthly cycles
    # Days of access kept after a failed renewal before the plan actually lapses.
    billing_grace_days: int = 3

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def billing_enabled(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret and self.razorpay_plan_id)

    @property
    def billing_is_test_mode(self) -> bool:
        return self.razorpay_key_id.startswith("rzp_test_")

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in ("prod", "production")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

# Fail fast rather than silently shipping a wide-open socket server to production.
if settings.is_production and "*" in settings.cors_origin_list:
    raise RuntimeError("CORS_ORIGINS must not contain '*' when APP_ENV is production")

# A production deployment taking real money with no webhook secret cannot verify that a
# payment notification actually came from Razorpay — anyone could POST themselves a plan.
if settings.is_production and settings.billing_enabled and not settings.razorpay_webhook_secret:
    raise RuntimeError("RAZORPAY_WEBHOOK_SECRET is required when billing is enabled")

# Test keys in production would silently take no money at all.
if settings.is_production and settings.billing_is_test_mode:
    raise RuntimeError("Razorpay test keys must not be used when APP_ENV is production")
