#include <Stepper.h>

const int stepsPerRevolution = 1600;  // количество шагов для одного полного оборота
Stepper myStepper(stepsPerRevolution, 3,4); // Пины подключения

const int buttonCW = 2; // Пин кнопки по часовой стрелке
const int buttonCCW = 5; // Пин кнопки против часовой стрелки

const int32_t stepsPerRound = 1600; // Total steps per full rotation
const int16_t stepChunk = 32000;

void setup() {
    pinMode(buttonCW, INPUT_PULLUP);   // Настройка пина кнопки по часовой стрелке
    pinMode(buttonCCW, INPUT_PULLUP);  // Настройка пина кнопки против часовой стрелки
    myStepper.setSpeed(6000);             // Установка скорости (об/мин)
    Serial.begin(9600);
}

void loop() {
    if (Serial.available()) {
        String command = Serial.readStringUntil('\n'); // Read command
        
        if (command == "CHECK") {
            Serial.println("ARDUINO"); // Respond to connection check
        } else {
            float rounds = command.toFloat();  // Convert command to float
            int32_t totalSteps = (int32_t)(rounds * stepsPerRound); // Convert rounds to steps
            int8_t direction = (totalSteps > 0) ? 1 : -1; // Determine direction

            Serial.print("MOVING ");
            Serial.println(totalSteps);

            totalSteps = abs(totalSteps); // Ensure positive step count
            
            while (totalSteps > 0) {
                int16_t stepsToMove = (totalSteps > stepChunk) ? stepChunk : totalSteps;
                Serial.println(stepsToMove * direction);
                myStepper.step(stepsToMove * direction);
                totalSteps -= stepsToMove;
            }

            Serial.println("DONE");
        }
    }
    if (digitalRead(buttonCW) == LOW) { // Если кнопка по часовой стрелке нажата
        myStepper.step(1);                 // Вращаем мотор на один шаг по часовой стрелке
    }
    
    if (digitalRead(buttonCCW) == LOW) { // Если кнопка против часовой стрелки нажата
        myStepper.step(-1);                // Вращаем мотор на один шаг против часовой стрелки
    }
}
