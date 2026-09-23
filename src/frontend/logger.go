package main

import (
	"os"
	"time"

	"github.com/sirupsen/logrus"
)

// log is initialised as a package-level variable (not in an init()) so it is
// ready before any init() in this package runs and logs.
var log = newLogger()

func newLogger() *logrus.Logger {
	l := logrus.New()
	l.Level = logrus.DebugLevel
	l.Formatter = &logrus.JSONFormatter{
		FieldMap: logrus.FieldMap{
			logrus.FieldKeyTime:  "timestamp",
			logrus.FieldKeyLevel: "severity",
			logrus.FieldKeyMsg:   "message",
		},
		TimestampFormat: time.RFC3339Nano,
	}
	l.Out = os.Stdout
	return l
}
