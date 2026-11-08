import pygame
import RPi.GPIO as GPIO
import time

# Initialize pygame mixer for audio playback
pygame.mixer.init()

# Define paths to your audio files
notes = {
    1: "/home/winnetka/notes/note1.wav",
    2: "/home/winnetka/notes/note2.wav",
    3: "/home/winnetka/notes/note3.wav",
    4: "/home/winnetka/notes/note4.wav",
    5: "/home/winnetka/notes/note5.wav",
    6: "/home/winnetka/notes/note6.wav",
    7: "/home/winnetka/notes/note7.wav",
    8: "/home/winnetka/notes/note8.wav",
}

# Define GPIO pins connected to the buttons
button_pins = [26, 17, 13, 22, 4, 5, 6, 27]

# Setup GPIO
GPIO.setmode(GPIO.BCM)  # Use BCM GPIO numbering
for pin in button_pins:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)  # Internal pull-up resistors

# Preload sounds for each note
sound_objects = {pin: pygame.mixer.Sound(notes[i + 1]) for i, pin in enumerate(button_pins)}

# Track button states
button_states = {pin: GPIO.HIGH for pin in button_pins}

def play_note_once(sound):
    """Play a sound without interruption."""
    sound.play()
    print(f"Sound {sound} played!")

def main():
    try:
        print("Bell system ready! Press a button to play a note.")
        while True:
            for pin in button_pins:
                current_state = GPIO.input(pin)
                if current_state == GPIO.LOW and button_states[pin] == GPIO.HIGH:
                    # Button was just pressed
                    play_note_once(sound_objects[pin])
                button_states[pin] = current_state
            yield
    except KeyboardInterrupt:
        print("Exiting program.")
    finally:
        GPIO.cleanup()  # Reset GPIO pins to a safe state

if __name__ == "__main__":
    main()
