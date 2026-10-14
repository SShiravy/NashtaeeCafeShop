"""Poll template, and the poll the bot asks (POLL, at the end of this file).

Every user can answer a poll once; a poll with a new key is a new poll.
"""

from dataclasses import dataclass, field


@dataclass(slots=True, frozen=True)
class PollQuestion:
    text: str
    options: list[str] = field(default_factory=list)  # empty: answered by typing
    optional: bool = False  # a typed answer can be skipped


@dataclass(slots=True, frozen=True)
class PollSection:
    title: str  # "" shows no section heading
    questions: list[PollQuestion]
    description: str = ""


@dataclass(slots=True, frozen=True)
class Poll:
    key: str  # saved with every response
    title: str
    sections: list[PollSection]

    @property
    def questions(self) -> list[tuple[PollSection, PollQuestion]]:
        """Every question with its section, in the order they are asked."""
        return [
            (section, question)
            for section in self.sections
            for question in section.questions
        ]


@dataclass(slots=True, frozen=True)
class PollAnswer:
    question_number: int  # 1-based, as shown to the user
    question: str
    answer: str


@dataclass(slots=True, frozen=True)
class PollResponse:
    """One user's finished poll; skipped questions have no answer."""

    poll: str  # Poll.key
    chat_id: str
    telegram_name: str
    telegram_username: str | None
    answers: list[PollAnswer]


POLL = Poll(
    key="breakfast_survey_1",
    title="نظرسنجی ناشتایی",
    sections=[
        PollSection(
            title="بخش اول: آشنایی با ناشتایی",
            description="می‌خواهیم بدانیم از کجا باید ارتباطمان را با شما شروع کنیم.",
            questions=[
                PollQuestion(
                    "قبل از این نظرسنجی، چقدر با ناشتایی آشنا بودید؟",
                    [
                        "مشتری ناشتایی هستم و قبلاً سفارش داده‌ام.",
                        "اسم ناشتایی را شنیده‌ام، اما هنوز سفارش نداده‌ام.",
                        "تازه با ناشتایی آشنا شده‌ام.",
                        "تا قبل از این پیام، ناشتایی را نمی‌شناختم.",
                    ],
                ),
                PollQuestion(
                    "اگر قبلاً ناشتایی را می‌شناختید، از چه طریقی؟",
                    [
                        "تازه از طریق همین پیام یا نظرسنجی",
                        "معرفی همکاران یا دوستان",
                        "شبکه‌های اجتماعی یا گروه‌های شهرک",
                        "دیدن محل یا خرید قبلی",
                        "قبلاً نمی‌شناختم",
                    ],
                ),
            ],
        ),
        PollSection(
            title="بخش دوم: عادت و رفتار خرید",
            description="برای اینکه بفهمیم نیاز واقعی شما چیست.",
            questions=[
                PollQuestion(
                    "در یک هفته معمولی، چند روز در محل کار صبحانه می‌خورید؟",
                    [
                        "۵ روز یا بیشتر",
                        "۲ تا ۳ روز",
                        "معمولاً یک روز",
                        "به‌ندرت یا اصلاً",
                    ],
                ),
                PollQuestion(
                    "معمولاً صبحانه محل کارتان را چطور تأمین می‌کنید؟",
                    [
                        "از خانه می‌آورم.",
                        "از بیرون خرید می‌کنم.",
                        "از بوفه یا غذاخوری محل کار تهیه می‌کنم.",
                        "اغلب صبحانه نمی‌خورم.",
                        "بسته به روز، ترکیبی از این روش‌ها",
                    ],
                ),
            ],
        ),
        PollSection(
            title="بخش سوم: موانع و اولویت‌ها",
            description=(
                "این بخش کمک می‌کند بفهمیم چرا ممکن است یک گزینه غذایی را انتخاب نکنید."
            ),
            questions=[
                PollQuestion(
                    "صادقانه بگویید، مهم‌ترین مانع شما برای داشتن صبحانه بهتر"
                    " در محل کار چیست؟",
                    [
                        "کمبود وقت و شلوغی ابتدای روز",
                        "قیمت و هزینه تکرارشونده خرید غذا",
                        "نگرانی درباره کیفیت، تازگی یا مواد اولیه",
                        "پیدا نکردن غذای متناسب با ترجیحات تغذیه‌ای",
                        "تکراری بودن گزینه‌ها",
                        "نامشخص بودن زمان تحویل یا دیر رسیدن سفارش",
                        "عادت ندارم در محل کار صبحانه بخورم.",
                    ],
                ),
                PollQuestion(
                    "اگر مجبور باشید فقط یکی را انتخاب کنید، کدام عامل در تصمیم خرید"
                    " شما تعیین‌کننده‌تر است؟",
                    [
                        "قیمت نهایی",
                        "طعم و خوشمزگی",
                        "کیفیت مواد اولیه و شیوه آماده‌سازی",
                        "تغذیه متعادل و ترکیبات غذا",
                        "تحویل دقیق و سریع",
                        "اعتماد به فروشنده و ثبات کیفیت",
                    ],
                ),
                PollQuestion(
                    "معمولاً چه زمانی به صبحانه نیاز دارید؟",
                    [
                        "قبل از ساعت ۹",
                        "ساعت ۹ تا ۱۰",
                        "بعد از ساعت ۱۰",
                        "زمان ثابتی ندارم.",
                    ],
                ),
            ],
        ),
        PollSection(
            title="بخش چهارم: اعتماد و تجربه خرید",
            questions=[
                PollQuestion(
                    "چه چیزی احتمال اینکه از یک مجموعه غذایی جدید خرید کنید را"
                    " بیشتر می‌کند؟",
                    [
                        "یک بار امتحان‌کردن با هزینه منطقی",
                        "توصیه همکار یا دوست مورداعتماد",
                        "دیدن تصاویر واقعی غذا و بسته‌بندی",
                        "اطلاع روشن از قیمت، ترکیبات و زمان تحویل",
                        "بازخورد مشتریان قبلی",
                        "اطمینان از ثبات کیفیت در سفارش‌های بعدی",
                    ],
                ),
                PollQuestion(
                    "چه نوع سفارشی برای شما کاربردی‌تر است؟",
                    [
                        "سفارش شخصی و موردی",
                        "پیش‌سفارش از روز قبل",
                        "سفارش مشترک با همکاران",
                        "سفارش هماهنگ‌شده برای شرکت یا واحد",
                    ],
                ),
                PollQuestion(
                    "اگر ناشتایی فقط یک مورد را بهتر کند تا برای شما انتخاب جذاب‌تری"
                    " شود، آن مورد چیست؟",
                    [
                        "گزینه‌های متنوع با توجه بیشتر به تغذیه",
                        "گزینه اقتصادی‌تر",
                        "تحویل منظم‌تر و قابل‌پیش‌بینی",
                        "منوی متنوع‌تر",
                        "فرایند سفارش ساده‌تر",
                        "در حال حاضر نیاز خاصی ندارم.",
                    ],
                ),
            ],
        ),
        PollSection(
            title="",
            questions=[
                PollQuestion(
                    "اگر یک مشکل یا دغدغه درباره صبحانه و ناهار محل کارتان دارید که"
                    " در سؤال‌های بالا نبود، یا اگر پیشنهادی دارید که باعث می‌شود"
                    " ناشتایی برای شما مفیدتر باشد، خوشحال می‌شویم اینجا برایمان"
                    " بنویسید",
                    optional=True,
                ),
            ],
        ),
    ],
)
