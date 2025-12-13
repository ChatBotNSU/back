from pydantic import BaseModel

class Message(BaseModel):
    text: str | None = None # text of the message
    images: list[str] | None = None # paths to the images
    audios: list[str] | None = None # paths to the audios
    files: list[str] | None = None # paths to the files

class InMessage(Message):
    restart_command: bool | None = None # flag showing if the message is a restart command

class OutMessage(Message):
    choise_options: list[str] | None = None # if set then choise options (buttons with messages to send) should be set for user in telegram. 
