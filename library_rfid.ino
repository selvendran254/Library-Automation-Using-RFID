// Library Automation Using RFID + Arduino + MFRC522

#include <SPI.h>
#include <MFRC522.h>
#include <LiquidCrystal_I2C.h>

#define SS_PIN 10
#define RST_PIN 9
MFRC522 rfid(SS_PIN, RST_PIN);

LiquidCrystal_I2C lcd(0x27,16,2);
String lastUID="";

void setup() {
  Serial.begin(9600);
  SPI.begin();
  rfid.PCD_Init();
  lcd.init();
  lcd.backlight();
  lcd.print("Library System");
}

String getUID(MFRC522::Uid uid){
  String s="";
  for(byte i=0;i<uid.size;i++){
    s+=String(uid.uidByte[i],HEX);
  }
  return s;
}

void loop() {
  if(!rfid.PICC_IsNewCardPresent()) return;
  if(!rfid.PICC_ReadCardSerial()) return;

  String uid=getUID(rfid.uid);
  uid.toUpperCase();

  lcd.clear();
  lcd.print("Tag: "); lcd.print(uid);
  Serial.print("RFID Scanned: "); Serial.println(uid);

  delay(2000);
  rfid.PICC_HaltA();
}
