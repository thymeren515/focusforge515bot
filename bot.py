import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, JobQueue

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Data file paths
TASKS_FILE = "tasks.json"
STATS_FILE = "stats.json"
ACHIEVEMENTS_FILE = "achievements.json"

# Data management functions
def load_data(file_path):
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

def save_data(file_path, data):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=2)

def load_tasks():
    return load_data(TASKS_FILE)

def save_tasks(tasks):
    save_data(TASKS_FILE, tasks)

def load_stats():
    return load_data(STATS_FILE)

def save_stats(stats):
    save_data(STATS_FILE, stats)

def load_achievements():
    return load_data(ACHIEVEMENTS_FILE)

def save_achievements(achievements):
    save_data(ACHIEVEMENTS_FILE, achievements)

# Achievement definitions
ACHIEVEMENT_DEFS = {
    'first_focus': {'name': '🎯 First Focus', 'desc': 'Complete your first focus session', 'icon': '🎯'},
    'seven_streak': {'name': '🔥 7-Day Streak', 'desc': 'Focus 7 days in a row', 'icon': '🔥'},
    'focus_master': {'name': '⚡ Focus Master', 'desc': 'Complete 50 focus sessions', 'icon': '⚡'},
    'task_ace': {'name': '📋 Task Ace', 'desc': 'Complete 100 tasks', 'icon': '📋'},
    'productivity_pro': {'name': '🏆 Productivity Pro', 'desc': '30 days active', 'icon': '🏆'},
    'marathon': {'name': '🏃 Focus Marathon', 'desc': 'Complete a 2-hour focus session', 'icon': '🏃'},
    'early_bird': {'name': '🌅 Early Bird', 'desc': 'Complete a focus session before 6 AM', 'icon': '🌅'},
    'night_owl': {'name': '🦉 Night Owl', 'desc': 'Complete a focus session after 11 PM', 'icon': '🦉'},
}

# Pomodoro settings
POMODORO_WORK = 25  # minutes
POMODORO_BREAK = 5  # minutes
POMODORO_LONG_BREAK = 15  # minutes

# Active sessions storage (in-memory)
active_sessions = {}

# Task management functions
def add_task(user_id, title, priority='normal'):
    """Add a new task"""
    tasks = load_tasks()
    user_id = str(user_id)
    
    if user_id not in tasks:
        tasks[user_id] = []
    
    task = {
        'id': len(tasks[user_id]) + 1,
        'title': title,
        'priority': priority,
        'created_at': datetime.now().isoformat(),
        'completed': False,
        'completed_at': None
    }
    
    tasks[user_id].append(task)
    save_tasks(tasks)
    return task

def get_tasks(user_id, include_completed=False):
    """Get user tasks"""
    tasks = load_tasks()
    user_id = str(user_id)
    
    if user_id not in tasks:
        return []
    
    if include_completed:
        return tasks[user_id]
    
    return [t for t in tasks[user_id] if not t['completed']]

def complete_task(user_id, task_id):
    """Mark a task as complete"""
    tasks = load_tasks()
    user_id = str(user_id)
    
    if user_id not in tasks:
        return False
    
    for task in tasks[user_id]:
        if task['id'] == task_id and not task['completed']:
            task['completed'] = True
            task['completed_at'] = datetime.now().isoformat()
            save_tasks(tasks)
            return True
    
    return False

def delete_task(user_id, task_id):
    """Delete a task"""
    tasks = load_tasks()
    user_id = str(user_id)
    
    if user_id not in tasks:
        return False
    
    tasks[user_id] = [t for t in tasks[user_id] if t['id'] != task_id]
    save_tasks(tasks)
    return True

# Statistics functions
def update_stats(user_id, session_type, duration):
    """Update user statistics"""
    stats = load_stats()
    user_id = str(user_id)
    
    if user_id not in stats:
        stats[user_id] = {
            'total_sessions': 0,
            'total_focus_time': 0,
            'total_breaks': 0,
            'tasks_completed': 0,
            'current_streak': 0,
            'best_streak': 0,
            'last_session_date': None,
            'sessions_by_day': {},
            'achievements': [],
            'active_days': 0,
            'first_focus_date': None
        }
    
    user_stats = stats[user_id]
    
    if session_type == 'focus':
        user_stats['total_sessions'] += 1
        user_stats['total_focus_time'] += duration
        
        # Track daily sessions
        today = datetime.now().strftime('%Y-%m-%d')
        if today not in user_stats['sessions_by_day']:
            user_stats['sessions_by_day'][today] = 0
        user_stats['sessions_by_day'][today] += 1
        
        # Track first focus date
        if not user_stats.get('first_focus_date'):
            user_stats['first_focus_date'] = datetime.now().isoformat()
        
        # Update streak
        if user_stats['last_session_date']:
            last_date = datetime.fromisoformat(user_stats['last_session_date']).date()
            today_date = datetime.now().date()
            
            if (today_date - last_date).days <= 1:
                user_stats['current_streak'] += 1
            else:
                user_stats['current_streak'] = 1
        else:
            user_stats['current_streak'] = 1
        
        if user_stats['current_streak'] > user_stats['best_streak']:
            user_stats['best_streak'] = user_stats['current_streak']
        
        user_stats['last_session_date'] = datetime.now().isoformat()
        
        # Update active days
        today = datetime.now().date()
        if user_stats.get('first_focus_date'):
            first_date = datetime.fromisoformat(user_stats['first_focus_date']).date()
            user_stats['active_days'] = (today - first_date).days + 1
    
    elif session_type == 'break':
        user_stats['total_breaks'] += 1
    
    elif session_type == 'task':
        user_stats['tasks_completed'] += 1
    
    # Check achievements
    check_achievements(user_id, user_stats)
    
    save_stats(stats)
    return user_stats

def check_achievements(user_id, user_stats):
    """Check and unlock achievements"""
    achievements = load_achievements()
    user_id = str(user_id)
    
    if user_id not in achievements:
        achievements[user_id] = []
    
    unlocked = achievements[user_id]
    
    # Check each achievement
    for key, defs in ACHIEVEMENT_DEFS.items():
        if key in unlocked:
            continue
        
        should_unlock = False
        
        if key == 'first_focus' and user_stats['total_sessions'] >= 1:
            should_unlock = True
        elif key == 'seven_streak' and user_stats['best_streak'] >= 7:
            should_unlock = True
        elif key == 'focus_master' and user_stats['total_sessions'] >= 50:
            should_unlock = True
        elif key == 'task_ace' and user_stats['tasks_completed'] >= 100:
            should_unlock = True
        elif key == 'productivity_pro' and user_stats['active_days'] >= 30:
            should_unlock = True
        elif key == 'marathon' and user_stats.get('longest_session', 0) >= 120:
            should_unlock = True
        elif key == 'early_bird' and user_stats.get('early_sessions', 0) >= 1:
            should_unlock = True
        elif key == 'night_owl' and user_stats.get('night_sessions', 0) >= 1:
            should_unlock = True
        
        if should_unlock:
            unlocked.append(key)
            achievements[user_id] = unlocked
            save_achievements(achievements)

def get_achievements(user_id):
    """Get user achievements"""
    achievements = load_achievements()
    user_id = str(user_id)
    return achievements.get(user_id, [])

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message"""
    user = update.effective_user
    
    welcome_text = (
        f"⚡ *Hi {user.first_name}! Welcome to Focus Forge!*\n\n"
        f"Your ultimate productivity companion! 🚀\n\n"
        f"*Features:*\n"
        f"🍅 Pomodoro Timer - 25/5 work/break cycles\n"
        f"📝 Task Management - Create and track tasks\n"
        f"⏰ Custom Focus Sessions\n"
        f"📊 Productivity Statistics\n"
        f"🔥 Streak Tracking\n"
        f"🏆 Achievement System\n\n"
        f"*Quick Start:*\n"
        f"• `/focus 25` - Start a focus session\n"
        f"• `/task Write report` - Add a task\n"
        f"• `/tasks` - View your tasks\n"
        f"• `/stats` - Your productivity stats\n"
        f"• `/streak` - See your focus streak\n\n"
        f"Let's get productive! 💪"
    )
    
    keyboard = [
        [InlineKeyboardButton("🍅 Start Pomodoro", callback_data="pomodoro")],
        [InlineKeyboardButton("⚡ Quick Focus (25min)", callback_data="focus_25")],
        [InlineKeyboardButton("📝 Manage Tasks", callback_data="tasks_menu")],
        [InlineKeyboardButton("📊 My Stats", callback_data="my_stats")],
        [InlineKeyboardButton("🏆 Achievements", callback_data="achievements")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def focus_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a focus session"""
    user = update.effective_user
    user_id = str(user.id)
    
    # Check if user already has an active session
    if user_id in active_sessions:
        await update.message.reply_text(
            "⏳ *You already have an active focus session!*\n\n"
            "Wait for it to finish or use /stopfocus to cancel.",
            parse_mode="Markdown"
        )
        return
    
    # Get duration from command or default to 25
    duration = 25
    if context.args and context.args[0].isdigit():
        duration = int(context.args[0])
        if duration < 1:
            duration = 1
        elif duration > 120:
            duration = 120
    
    # Start the session
    end_time = datetime.now() + timedelta(minutes=duration)
    
    active_sessions[user_id] = {
        'start_time': datetime.now(),
        'duration': duration,
        'end_time': end_time,
        'type': 'focus'
    }
    
    # Schedule end notification
    context.job_queue.run_once(
        end_focus_session,
        duration * 60,
        context={'user_id': user_id, 'chat_id': update.effective_chat.id}
    )
    
    # Schedule reminder at halfway point
    if duration > 5:
        context.job_queue.run_once(
            focus_reminder,
            (duration // 2) * 60,
            context={'user_id': user_id, 'chat_id': update.effective_chat.id}
        )
    
    # Send confirmation
    response = (
        f"⏰ *Focus session started!*\n\n"
        f"⏱️ Duration: {duration} minutes\n"
        f"🕒 Ends at: {end_time.strftime('%I:%M %p')}\n\n"
        f"💪 Stay focused! You've got this!\n"
        f"🔔 I'll remind you when time's up."
    )
    
    await update.message.reply_text(response, parse_mode="Markdown")

async def end_focus_session(context: ContextTypes.DEFAULT_TYPE) -> None:
    """End a focus session"""
    job_data = context.job.data
    user_id = job_data['user_id']
    chat_id = job_data['chat_id']
    
    if user_id not in active_sessions:
        return
    
    session = active_sessions[user_id]
    duration = session['duration']
    
    # Update stats
    stats = update_stats(user_id, 'focus', duration)
    
    # Remove from active sessions
    del active_sessions[user_id]
    
    # Check if this is a long session for achievement
    if duration >= 120:
        stats['longest_session'] = duration
        save_stats(load_stats())
    
    # Send completion message
    response = (
        f"🎉 *Focus session complete!*\n\n"
        f"⏱️ Duration: {duration} minutes\n"
        f"📊 Total sessions: {stats['total_sessions']}\n"
        f"🔥 Current streak: {stats['current_streak']} days\n\n"
        f"🍅 Take a break with /break\n"
        f"📝 Review your tasks with /tasks\n\n"
        f"Great job staying focused! 💪"
    )
    
    await context.bot.send_message(chat_id=chat_id, text=response, parse_mode="Markdown")

async def focus_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send focus reminder"""
    job_data = context.job.data
    user_id = job_data['user_id']
    chat_id = job_data['chat_id']
    
    if user_id not in active_sessions:
        return
    
    session = active_sessions[user_id]
    elapsed = int((datetime.now() - session['start_time']).total_seconds() / 60)
    total = session['duration']
    
    response = (
        f"⏰ *Focus update!*\n\n"
        f"📊 {elapsed}/{total} minutes elapsed\n"
        f"💪 You're doing great! Keep going!\n"
        f"🎯 Stay focused on your goal."
    )
    
    await context.bot.send_message(chat_id=chat_id, text=response, parse_mode="Markdown")

async def break_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a break timer"""
    user = update.effective_user
    user_id = str(user.id)
    
    # Get break duration (default 5 min)
    duration = 5
    if context.args and context.args[0].isdigit():
        duration = int(context.args[0])
        if duration < 1:
            duration = 1
        elif duration > 30:
            duration = 30
    
    # Schedule break end
    end_time = datetime.now() + timedelta(minutes=duration)
    context.job_queue.run_once(
        end_break_session,
        duration * 60,
        context={'user_id': user_id, 'chat_id': update.effective_chat.id}
    )
    
    # Update stats
    update_stats(user_id, 'break', duration)
    
    response = (
        f"☕ *Break time!*\n\n"
        f"⏱️ Duration: {duration} minutes\n"
        f"🕒 Ends at: {end_time.strftime('%I:%M %p')}\n\n"
        f"🧘 Relax and recharge!\n"
        f"🔔 I'll remind you when break is over."
    )
    
    await update.message.reply_text(response, parse_mode="Markdown")

async def end_break_session(context: ContextTypes.DEFAULT_TYPE) -> None:
    """End a break session"""
    job_data = context.job.data
    user_id = job_data['user_id']
    chat_id = job_data['chat_id']
    
    response = (
        f"⏰ *Break time is over!*\n\n"
        f"💪 Ready to focus again?\n"
        f"Start a new session with /focus\n"
        f"📝 Or check your tasks with /tasks"
    )
    
    await context.bot.send_message(chat_id=chat_id, text=response, parse_mode="Markdown")

async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a new task"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ *Please provide a task title!*\n\n"
            "Usage: `/task Title of the task`\n"
            "Example: `/task Write project proposal`\n\n"
            "You can also add priority:\n"
            "`/task Title --high` or `--low`",
            parse_mode="Markdown"
        )
        return
    
    # Parse task title and priority
    full_text = " ".join(context.args)
    priority = 'normal'
    title = full_text
    
    if '--high' in full_text:
        priority = 'high'
        title = full_text.replace('--high', '').strip()
    elif '--low' in full_text:
        priority = 'low'
        title = full_text.replace('--low', '').strip()
    elif '--medium' in full_text:
        priority = 'medium'
        title = full_text.replace('--medium', '').strip()
    
    # Add the task
    task = add_task(user.id, title, priority)
    
    priority_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢', 'normal': '🔵'}
    emoji = priority_emoji.get(priority, '🔵')
    
    response = (
        f"✅ *Task added successfully!*\n\n"
        f"📝 {emoji} {title}\n"
        f"📊 Priority: {priority.upper()}\n"
        f"🆔 ID: {task['id']}\n\n"
        f"📋 View all tasks: /tasks\n"
        f"✅ Mark as done: /done {task['id']}"
    )
    
    await update.message.reply_text(response, parse_mode="Markdown")

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View user tasks"""
    user = update.effective_user
    
    tasks = get_tasks(user.id)
    
    if not tasks:
        await update.message.reply_text(
            "📝 *No active tasks!*\n\n"
            "Add a task with:\n"
            "`/task Your task title`\n\n"
            "Example: `/task Read chapter 5`",
            parse_mode="Markdown"
        )
        return
    
    response = "📋 *Your Active Tasks*\n\n"
    
    for task in tasks:
        priority_emoji = {'high': '🔴', 'medium': '🟡', 'low': '🟢', 'normal': '🔵'}
        emoji = priority_emoji.get(task['priority'], '🔵')
        response += f"{emoji} *{task['id']}.* {task['title']}\n"
        response += f"   Priority: {task['priority'].upper()}\n"
    
    response += "\n✅ Complete a task: `/done task_id`\n"
    response += "🗑️ Delete a task: `/delete task_id`"
    
    await update.message.reply_text(response, parse_mode="Markdown")

async def done_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mark a task as complete"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ *Please provide a task ID!*\n\n"
            "Usage: `/done task_id`\n"
            "Example: `/done 1`\n\n"
            "📋 View your tasks with: /tasks",
            parse_mode="Markdown"
        )
        return
    
    try:
        task_id = int(context.args[0])
        if complete_task(user.id, task_id):
            # Update stats
            update_stats(user.id, 'task', 0)
            
            await update.message.reply_text(
                f"✅ *Task {task_id} completed!*\n\n"
                f"🎉 Great job! Keep up the momentum!\n"
                f"📊 Check your stats with /stats",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❌ *Task {task_id} not found or already completed!*\n\n"
                f"📋 Check your tasks with /tasks",
                parse_mode="Markdown"
            )
    except ValueError:
        await update.message.reply_text(
            "❌ *Invalid task ID!*\n\n"
            "Please provide a number.\n"
            "Example: `/done 1`",
            parse_mode="Markdown"
        )

async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a task"""
    user = update.effective_user
    
    if not context.args:
        await update.message.reply_text(
            "❌ *Please provide a task ID!*\n\n"
            "Usage: `/delete task_id`\n"
            "Example: `/delete 1`",
            parse_mode="Markdown"
        )
        return
    
    try:
        task_id = int(context.args[0])
        if delete_task(user.id, task_id):
            await update.message.reply_text(
                f"🗑️ *Task {task_id} deleted!*",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                f"❌ *Task {task_id} not found!*",
                parse_mode="Markdown"
            )
    except ValueError:
        await update.message.reply_text(
            "❌ *Invalid task ID!*\n\n"
            "Please provide a number.",
            parse_mode="Markdown"
        )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user statistics"""
    user = update.effective_user
    user_id = str(user.id)
    
    stats = load_stats()
    
    if user_id not in stats:
        await update.message.reply_text(
            "📊 *No stats yet!*\n\n"
            "Start a focus session with /focus to build your statistics! 💪",
            parse_mode="Markdown"
        )
        return
    
    user_stats = stats[user_id]
    
    # Calculate averages
    total_sessions = user_stats['total_sessions']
    total_time = user_stats['total_focus_time']
    avg_time = total_time / total_sessions if total_sessions > 0 else 0
    
    # Get today's sessions
    today = datetime.now().strftime('%Y-%m-%d')
    today_sessions = user_stats['sessions_by_day'].get(today, 0)
    
    stats_text = (
        f"📊 *Productivity Statistics*\n\n"
        f"🍅 Total Sessions: {total_sessions}\n"
        f"⏱️ Total Focus Time: {total_time} min\n"
        f"📈 Average Session: {avg_time:.1f} min\n"
        f"📅 Today's Sessions: {today_sessions}\n"
        f"🔥 Current Streak: {user_stats['current_streak']} days\n"
        f"🏆 Best Streak: {user_stats['best_streak']} days\n"
        f"🎯 Tasks Completed: {user_stats['tasks_completed']}\n"
        f"📆 Active Days: {user_stats['active_days']}\n\n"
        f"💪 Keep going! You're building great habits!"
    )
    
    await update.message.reply_text(stats_text, parse_mode="Markdown")

async def streak_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show focus streak"""
    user = update.effective_user
    user_id = str(user.id)
    
    stats = load_stats()
    
    if user_id not in stats:
        await update.message.reply_text(
            "🔥 *No streak yet!*\n\n"
            "Start your first focus session to begin your streak!",
            parse_mode="Markdown"
        )
        return
    
    user_stats = stats[user_id]
    current = user_stats['current_streak']
    best = user_stats['best_streak']
    
    # Get last session date
    last_date = "Never"
    if user_stats.get('last_session_date'):
        last_date = datetime.fromisoformat(user_stats['last_session_date']).strftime('%B %d, %Y')
    
    # Create visual streak bar
    bar = "🔥" * min(current, 10) + "⬜" * max(0, 10 - min(current, 10))
    
    response = (
        f"🔥 *Focus Streak*\n\n"
        f"📊 Current Streak: {current} days\n"
        f"🏆 Best Streak: {best} days\n"
        f"📅 Last Session: {last_date}\n\n"
        f"{bar}\n\n"
        f"💪 Keep the streak alive! Focus daily!\n"
        f"🎯 Next milestone: {((current // 7) + 1) * 7} days"
    )
    
    await update.message.reply_text(response, parse_mode="Markdown")

async def achievements_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user achievements"""
    user = update.effective_user
    user_id = str(user.id)
    
    unlocked = get_achievements(user_id)
    all_achievements = ACHIEVEMENT_DEFS
    
    response = "🏆 *Achievements*\n\n"
    
    # Show unlocked achievements
    if unlocked:
        response += "✅ *Unlocked*\n"
        for key in unlocked:
            if key in all_achievements:
                defs = all_achievements[key]
                response += f"{defs['icon']} {defs['name']} - {defs['desc']}\n"
        response += "\n"
    
    # Show locked achievements
    locked = [k for k in all_achievements.keys() if k not in unlocked]
    if locked:
        response += "🔒 *Locked*\n"
        for key in locked:
            defs = all_achievements[key]
            response += f"{defs['icon']} {defs['name']} - {defs['desc']}\n"
    else:
        response += "🎉 *You've unlocked all achievements! Amazing!*"
    
    await update.message.reply_text(response, parse_mode="Markdown")

async def stopfocus_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Cancel current focus session"""
    user = update.effective_user
    user_id = str(user.id)
    
    if user_id in active_sessions:
        del active_sessions[user_id]
        await update.message.reply_text(
            "⏹️ *Focus session cancelled.*\n\n"
            "You can start a new session anytime with /focus",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "❌ *No active focus session found!*",
            parse_mode="Markdown"
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help message"""
    help_text = (
        "⚡ *Focus Forge - Help*\n\n"
        "📋 *Commands:*\n"
        "• /start - Welcome menu\n"
        "• /focus [minutes] - Start focus session\n"
        "• /break [minutes] - Start break timer\n"
        "• /task [title] - Add a task\n"
        "• /tasks - View all tasks\n"
        "• /done [id] - Complete a task\n"
        "• /delete [id] - Delete a task\n"
        "• /stats - View statistics\n"
        "• /streak - Check your streak\n"
        "• /achievements - View achievements\n"
        "• /stopfocus - Stop current session\n"
        "• /help - This menu\n\n"
        "🍅 *Pomodoro Features:*\n"
        "• Work: 25 min, Break: 5 min\n"
        "• Long break after 4 cycles: 15 min\n"
        "• Custom session lengths supported\n\n"
        "📝 *Task Priority:*\n"
        "• --high, --medium, --low\n"
        "• Example: `/task Read --high`\n\n"
        "🏆 *Achievements:*\n"
        "• Unlock achievements for milestones\n"
        "• Track your progress\n\n"
        "💡 *Tips:*\n"
        "• Use /focus 10 for a quick session\n"
        "• Set daily tasks to stay organized\n"
        "• Check your stats to stay motivated"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def pomodoro_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start a full Pomodoro cycle"""
    user = update.effective_user
    user_id = str(user.id)
    
    if user_id in active_sessions:
        await update.message.reply_text(
            "⏳ *You already have an active focus session!*\n\n"
            "Wait for it to finish or use /stopfocus to cancel.",
            parse_mode="Markdown"
        )
        return
    
    # Start 25 min focus
    context.user_data['pomodoro_cycle'] = 1
    await focus_command(update, context)
    
    # Schedule break notification
    context.job_queue.run_once(
        pomodoro_break_reminder,
        POMODORO_WORK * 60 + 10,  # Just before work ends
        context={'user_id': user_id, 'chat_id': update.effective_chat.id}
    )

async def pomodoro_break_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remind user to take a break"""
    job_data = context.job.data
    user_id = job_data['user_id']
    chat_id = job_data['chat_id']
    
    if user_id not in active_sessions:
        return
    
    response = (
        f"☕ *Time for a break!*\n\n"
        f"Your 25-minute focus session is almost complete.\n"
        f"Take a {POMODORO_BREAK} minute break!\n\n"
        f"🧘 Relax, stretch, recharge!\n"
        f"🔔 I'll remind you when break is over."
    )
    
    await context.bot.send_message(chat_id=chat_id, text=response, parse_mode="Markdown")

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button presses"""
    query = update.callback_query
    await query.answer()
    user = query.from_user
    chat_id = update.effective_chat.id
    
    if query.data == "pomodoro":
        # Start Pomodoro
        await pomodoro_start(update, context)
    
    elif query.data == "focus_25":
        # Quick 25-min focus
        context.args = ['25']
        await focus_command(update, context)
    
    elif query.data == "tasks_menu":
        # Show tasks
        await tasks_command(update, context)
    
    elif query.data == "my_stats":
        await stats_command(update, context)
    
    elif query.data == "achievements":
        await achievements_command(update, context)
    
    elif query.data.startswith("focus_"):
        # Custom focus from buttons
        duration = int(query.data.split("_")[1])
        context.args = [str(duration)]
        await focus_command(update, context)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle errors"""
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ *An error occurred!*\n\n"
            "Please try again or contact support.\n"
            "If this persists, try using /start to begin a new session.",
            parse_mode="Markdown"
        )

def main() -> None:
    """Start the bot"""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("❌ No TELEGRAM_BOT_TOKEN found in environment variables!")
        return
    
    logger.info("🚀 Starting Focus Forge bot...")
    
    # Create application with job queue
    application = Application.builder().token(token).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("focus", focus_command))
    application.add_handler(CommandHandler("break", break_command))
    application.add_handler(CommandHandler("task", task_command))
    application.add_handler(CommandHandler("tasks", tasks_command))
    application.add_handler(CommandHandler("done", done_command))
    application.add_handler(CommandHandler("delete", delete_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("streak", streak_command))
    application.add_handler(CommandHandler("achievements", achievements_command))
    application.add_handler(CommandHandler("stopfocus", stopfocus_command))
    application.add_handler(CommandHandler("help", help_command))
    
    # Add button callback handler
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start polling
    logger.info("✅ Bot is running...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
